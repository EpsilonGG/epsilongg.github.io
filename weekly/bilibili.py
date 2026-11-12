"""B 站动态：周报的第二个数据源（只读展示层旁路）。

`data/bilibili/galgame/<JST 日>.jsonl` 是 B 站动态的正本，由
`scripts/bilibili_daily.py fetch` 落盘，键形如 `bilibili:<动态 id>`。
日报侧已经在「详细」里给 Galgame 版开了第三个栏目按钮；周报这一层
（2026-11-12 用户裁决）再开第四个展示栏「B站动态」。

为什么**不**把 B 站条目塞进 `weekly/corpus.py` 的 X 侧语料：

* 那套四类筛选 / 原推内容组去重 / 三值归栏有整套守恒断言与历史回测基线，
  混入一个没有 X handle、没有 M1 分句索引的数据源会把证据链全部漂掉；
* 用户明确要求「作品情报」「业界动向」两栏保持不变。

所以 B 站条目只在**展示层**单独成行：按当期日报覆盖的 JST 日逐日读正本，
每条压成单行，剥掉裸 URL（周报正文只允许 Markdown 链接）、归一书名号，
句首挂一条 `[发布者](B站原文)`；再按 `game_routing.new_work_labels()`
的**同一份**规则做游戏级「新作」过滤——命中的游戏整组进第一栏「新作」，
其余留在第四栏「B站动态」。

2026-11-12 追加口径（同日用户裁决）：**同一个账号的归到一起**，合并后超过
150 字就概括。周报的归并单位是「账号 × 作品小标题」——品牌中标题本身就是
账号，再按作品拆一格，才不会把不同游戏的条目混成一句、也才不会破坏
`new_work_labels()` 的游戏级判定。概括是纯规则（分额度取整句 → 骨架相同的
句子并成一条 → 超长从尾部丢整句），不调模型，同一份正本必得同一句话。

本模块不写 `data/daily/<期号>/report.json`，也不碰任何受保护的日报文件。
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path

from . import brackets
from .config import BILIBILI, BILI_VIEW, NEW, WORK
from .corpus import day_of, norm_title
from .game_routing import NO_GAME, new_work_labels

# URL 只吃 URL 合法的 ASCII 字符，遇到中文标点 / 空白就停，不会把后面的正文吞掉。
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.I)
# 话题标签整段是噪音（`#HIKARIFIELD# #GALGAME#`），正文里没有它的位置。
TAG_RE = re.compile(r"#[^\s#]{1,30}#")
# 零宽字符（B 站正文偶尔带 U+200B 开头），会让字数与显示都发毛。
ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\ufeff]")
# 作品名：`《》` 是作品 / 乐曲，`『』` 是本站统一的游戏名写法。
TITLE_RE = re.compile(r"《[^》]{1,60}》|『[^』]{1,60}』")
# 句末标点。断句用扫描器（见 `_sentences`），不能在书名号里面断——
# `《淑女同萌！-Superior Entelecheia-》` 名字里就带「！」，正则一断就变成
# 「《淑女同萌！」这种半截书名号，后面的骨架归并全跟着错。
SENTENCE_END = "。！？!?；;\n"
# 断句时要跳过的成对符号：里面出现的句末标点不算句子结束。
BRACKETS = {"《": "》", "『": "』", "【": "】", "〖": "〗", "［": "］", "「": "」"}
# 作品小标题只认『』：《》在周报里是乐曲 / 书籍，「」是角色或引语。
WORK_RE = re.compile(r"『([^』]{1,60})』")

# 合并后超过这个字数就概括（用户口径：150 字）。`rules.json:bilibili.summary_limit`
# 可以覆盖，但默认值就是裁决值，别在代码里另写一份别的数字。
SUMMARY_LIMIT = 150
# 概括时每个账号至少拿到的额度：账号再多也别把一句话切成半截。
MIN_CLAUSE_QUOTA = 40
# 相似句合并的阈值（字符 3-gram 的 Jaccard 系数）。
SIMILARITY = 0.7
# 包含度阈值：短句的 3-gram 有八成被长句包住，就当成同一句模板的重复。
CONTAINMENT = 0.8



def _display_title(title: str) -> str:
    """与 pipeline._display_title 同口径：拆散成对半角 `~`，避免渲染成 <del>。"""
    if "~" not in str(title or ""):
        return str(title or "")
    return " ".join(str(title).replace("~", " ~ ").split())


def clean_text(text: str, titles: set[str], bracket_cfg: dict) -> str:
    """一条 B 站动态 → 可直接进 `- ` 小条目的单行正文。

    四件事：换行压平、剥裸 URL、剥话题标签与零宽字符、书名号归一
    （归一函数幂等，check 会复核）。
    """
    parts: list[str] = []
    for raw in ZERO_WIDTH_RE.sub("", str(text or "")).splitlines():
        line = TAG_RE.sub("", URL_RE.sub("", raw.strip())).strip()
        line = re.sub(r"\s+", " ", line)
        if line:
            parts.append(line)
    joined = re.sub(r"\s+", " ", " ".join(parts)).strip()
    fixed, _ = brackets.normalize(joined, titles, bracket_cfg)
    return fixed.strip()


def _one_line(text: str) -> str:
    """`clean_text` 的轻量版（不归一书名号）：概括函数自己也能单独用。"""
    out = ZERO_WIDTH_RE.sub("", str(text or ""))
    out = TAG_RE.sub("", URL_RE.sub("", out))
    return re.sub(r"\s+", " ", out).strip()


def char_count(text: str) -> int:
    """字数：去掉空白后的字符数（中文一字一个）。"""
    return len(re.sub(r"\s+", "", str(text or "")))


def _sentences(text: str) -> list[str]:
    """按句末标点断句，**但不进书名号 / 方头括号里断**。

    理由见 `BRACKETS` 注释：`《淑女同萌！-Superior Entelecheia-》` 这类名字
    自带「！」，正则断句会把标题劈成两半，后面的骨架归并就全错了。
    未闭合的括号会让后面的内容并成一句，这是可接受的降级（概括照样截断）。
    """
    out: list[str] = []
    buf: list[str] = []
    closer = ""
    for char in str(text or ""):
        if closer:
            buf.append(char)
            if char == closer:
                closer = ""
            continue
        if char in BRACKETS:
            closer = BRACKETS[char]
            buf.append(char)
            continue
        buf.append(char)
        if char in SENTENCE_END:
            piece = "".join(buf).strip()
            if piece:
                out.append(piece)
            buf = []
    piece = "".join(buf).strip()
    if piece:
        out.append(piece)
    return out


def _skeleton(text: str) -> str:
    """去掉作品名后的「骨架」：六条不同作品的同款促销语，骨架一模一样。"""
    out = TITLE_RE.sub("", text)
    return re.sub(r"\s+", " ", out).strip().strip(" ，,、").strip()


def _trigrams(text: str) -> set[str]:
    body = re.sub(r"\s+", "", text)
    return {body[i:i + 3] for i in range(max(0, len(body) - 2))}


def _similar(left: str, right: str) -> bool:
    """骨架是不是「同一句模板」：要么整体相近，要么短的整段被长的包住。

    只用 Jaccard 会漏掉「同款模板 + 多一句补充」的情况（`体验版公开中！`
    对 `体验版公开中！▼下载请点这里…`），加一条包含度判据才盖得住。
    """
    if not left or not right:
        return False
    if left == right:
        return True
    a, b = _trigrams(left), _trigrams(right)
    if not a or not b:
        return False
    shared = len(a & b)
    return (shared / (len(a) + len(b) - shared) >= SIMILARITY
            or shared / min(len(a), len(b)) >= CONTAINMENT)


def _clip(text: str, limit: int) -> str:
    """硬截断时尽量切在句末，别留半句（「…首发折」这种）。"""
    if char_count(text) <= limit:
        return text
    cut = text[:limit]
    for mark in "。！？!?；;":
        index = cut.rfind(mark)
        if index >= int(limit * 0.6):
            return cut[:index + 1]
    return cut


def summarize(parts: list[str], limit: int = SUMMARY_LIMIT) -> tuple[str, bool]:
    """同一账号（同一格子）的若干条动态 → 一行 ≤limit 字的正文。

    规则与 `src/lib/bilibili-daily.ts:summarizeBilibili()` 同口径（日报、周报
    两层的读者看到的是同一种概括）：

    1. 合计 ≤ limit 就原样拼接，一个字都不改；
    2. 超了按条数分额度，每条先取整句（不足额度就顺延下一句）；
    3. **首句骨架**相同或高度相似的条目并成一条，作品名收进末尾括号
       （`官方中文版现正于官网商城促销热卖中！（《A》、《B》）`）——
       六条同款促销才不会被写成六行重复；
    4. 仍然超长就从尾部丢整句，末尾留一个省略号，绝不把句子切成半截。

    返回（正文, 是否概括）。
    """
    cleaned = [_one_line(part) for part in parts or []]
    cleaned = [part for part in cleaned if part]
    if not cleaned:
        return "", False
    full = " ".join(cleaned)
    if char_count(full) <= limit:
        return full, False

    quota = max(MIN_CLAUSE_QUOTA, limit // len(cleaned))
    merged: list[dict] = []
    for part in cleaned:
        sentences = _sentences(part)
        if not sentences:
            continue
        clause = ""
        for sentence in sentences:
            clause = clause + sentence
            if char_count(clause) >= quota:
                break
        # 归并判据只看**首句骨架**：促销贴的第二句常常是价格 / 链接说明，
        # 带上它会让「同一句模板」被拆成好几桶。作品名也只取首句里的——
        # 正文后半段提到的《游魂》《生命的备件》是代表作，不是这次宣传的作品。
        lead = sentences[0]
        key = _skeleton(lead)
        titles = list(dict.fromkeys(TITLE_RE.findall(lead)))
        hit = next((m for m in merged if _similar(m["key"], key)), None)
        if hit is None:
            merged.append({"text": clause, "key": key, "titles": titles, "count": 1})
        else:
            hit["count"] += 1
            for title in titles:
                if title not in hit["titles"]:
                    hit["titles"].append(title)

    clauses: list[str] = []
    for item in merged:
        if item["count"] == 1:
            clauses.append(item["text"])
            continue
        # 并起来的那条保留首句原文（信息最全），只在后面补「另：其余作品名」；
        # 已经出现在正文里的作品名不重复列。条数由行首的「共 N 条」统一交代，
        # 不再往句子中间塞「（共 10 条）」——那会把一句读成两截。
        extra = [title for title in item["titles"] if title not in item["text"]]
        clauses.append(f"{item['text']}（另：{'、'.join(extra)}）" if extra
                       else item["text"])
    if not clauses:
        return full, False

    joined = "；".join(clauses)
    if char_count(joined) <= limit:
        return joined, True

    # 留一个字给省略号，保证概括出来的整行不超过 limit。
    kept = ""
    for clause in clauses:
        candidate = clause if not kept else kept + "；" + clause
        if char_count(candidate) > limit - 1:
            break
        kept = candidate
    if not kept:
        kept = _clip(clauses[0] or "", max(0, limit - 1))
    return kept + "…", True


def source_files(issues: list[str]) -> list[tuple[str, Path]]:
    """当期 Galgame 日报覆盖的 JST 日 → 对应的 B 站正本文件（缺文件就跳过）。"""
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for issue in issues or []:
        day = day_of(issue)
        if day in seen:
            continue
        seen.add(day)
        path = BILIBILI / f"{day}.jsonl"
        if path.is_file():
            out.append((day, path))
    return out


def attach(corpus: dict, rules: dict) -> dict:
    """把 B 站正本以 `bilibili` / `bilibili_refs` 两个键挂到语料字典上。

    `bilibili_refs` 是给 `weekly check` 的外链白名单用的，`source_refs` 一个键都
    不加——X 侧源索引保持逐字不变。返回的是新字典，不改调用方手里的那份。
    """
    cfg = rules.get("bilibili") or {}
    rows: list[dict] = []
    refs: dict[str, dict] = {}
    if cfg.get("enabled", True):
        seen: set[str] = set()
        for day, path in source_files(corpus.get("issues") or []):
            for raw in path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                try:
                    rec = read_json_line(raw)
                except ValueError:
                    continue
                key = str(rec.get("identity_key") or "")
                url = str(rec.get("canonical_url") or "")
                content = str(rec.get("content") or "").strip()
                if not key.startswith("bilibili:") or not url or not content or key in seen:
                    continue
                seen.add(key)
                meta = rec.get("metadata") or {}
                publisher = str(rec.get("publisher") or "").strip() or "B站账号"
                handle = str(meta.get("account") or "")
                rows.append({
                    "key": key, "day": day, "url": url, "content": content,
                    "publisher": publisher, "handle": handle,
                    "published_at": str(rec.get("published_at") or ""),
                    "source_file": f"data/bilibili/galgame/{day}.jsonl",
                })
                refs[key] = {
                    "url": url, "text": content, "author": publisher,
                    "handle": handle, "published_at": str(rec.get("published_at") or ""),
                    "origin": "bilibili", "source_file": f"data/bilibili/galgame/{day}.jsonl",
                }
    rows.sort(key=lambda r: (r["day"], r["published_at"], r["key"]))
    payload = dict(corpus)
    payload["bilibili"] = rows
    payload["bilibili_refs"] = refs
    payload["stats"] = {**dict(corpus.get("stats") or {}), "bilibili_rows": len(rows)}
    return payload


def read_json_line(raw: str) -> dict:
    """单独抽出来方便测试造样本；坏行由调用方跳过，不让一条脏数据毁掉整期。"""
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


def build_lines(corpus: dict, rules: dict) -> list[dict]:
    """B 站动态 → 出稿 / 筛选页共用的展示行（Python 与内联 JS 读同一份）。

    每行已经带好 `column / brand / gkey / glabel / text`，两端都不再计算，
    所以 JS-Python parity 不会因为多一栏而出现两套口径。

    归并单位是「账号 × 作品小标题」（2026-11-12 用户口径「同个账号的归到一起」）：
    品牌中标题本身就是账号，再按作品拆一格，既不会把不同游戏混成一句，
    也不会破坏 `new_work_labels()` 的游戏级判定——`sentence` 仍是该格全部句子
    的拼接，信号该命中的一个不少。
    """
    cfg = rules.get("bilibili") or {}
    if not cfg.get("enabled", True) or not BILI_VIEW:
        return []
    limit = int(cfg.get("summary_limit") or SUMMARY_LIMIT)
    titles = set(corpus.get("titles") or [])
    bracket_cfg = rules.get("brackets") or {}
    prefix = str(cfg.get("brand_prefix") or "B站 · ")
    no_game = str(cfg.get("no_game_label") or "动态")

    cells: "OrderedDict[tuple[str, str], list[dict]]" = OrderedDict()
    for rec in corpus.get("bilibili") or []:
        text = clean_text(rec["content"], titles, bracket_cfg)
        if not text:
            continue
        match = WORK_RE.search(text)
        title = norm_title(match.group(1)) if match else ""
        glabel = f"『{_display_title(title)}』" if title else no_game
        # 路由用「未标注作品」这个名字，让 new_work_labels() 的 never 列表直接生效。
        route_game = glabel if title else NO_GAME
        brand = prefix + str(rec["publisher"])
        cells.setdefault((brand, glabel), []).append(
            {"rec": rec, "text": text, "glabel": glabel,
             "group_label": route_game, "brand": brand})

    rows: list[dict] = []
    for (brand, glabel), items in cells.items():
        sentences = [item["text"] for item in items]
        display, summarized = summarize(sentences, limit)
        if not display:
            continue
        first = items[0]["rec"]
        count = len(items)
        # 多条的格子标「共 N 条」，读者才知道这行是并起来的、不是原文一条。
        mark = f"（共 {count} 条）" if count > 1 else ""
        rows.append({
            "key": first["key"], "day": first["day"], "url": first["url"],
            "publisher": first["publisher"], "brand": brand,
            "gkey": "b:" + hashlib.md5(
                (brand + "|" + glabel).encode("utf-8")).hexdigest()[:12],
            "glabel": glabel, "group_label": items[0]["group_label"],
            # 信号判定读**逐条**的句子（不是拼接后的那句）：条件信号
            # （`公开新CG` 要看「当期还有没有别的消息」）依赖句子粒度，
            # 拼成一句会把「这条只有 CG、那条还有别的」读成「同一句既有 CG 又有别的」。
            "sentences": sentences,
            "sentence": " ".join(sentences),
            "text": ("- [" + str(first["publisher"]) + "](" + first["url"]
                     + ")" + mark + "：" + display),
            "count": count, "summarized": summarized,
            "keys": [item["rec"]["key"] for item in items],
        })

    # 游戏级「新作」过滤：与 X 侧出稿分流读同一个函数、同一份 rules.json 配置。
    # 传进去的是逐条动态，不是归并后的格子——见上面 `sentences` 的注释。
    pseudo = [{
        "column": WORK,
        "items": [{"group_label": r["group_label"], "sentence": s}
                  for r in rows for s in r["sentences"]],
    }]
    labels = new_work_labels(pseudo, rules.get("game_routing") or {}) if rows else set()
    lines: list[dict] = []
    for row in rows:
        is_new = row["group_label"] != NO_GAME and row["group_label"] in labels
        lines.append({
            "key": row["key"], "column": NEW if is_new else BILI_VIEW,
            "brand": row["brand"], "gkey": row["gkey"], "glabel": row["glabel"],
            "text": row["text"], "official": False, "new_work": is_new,
            "day": row["day"], "url": row["url"], "publisher": row["publisher"],
            "group_label": row["group_label"], "count": row["count"],
            "summarized": row["summarized"], "keys": row["keys"],
            "sentences": row["sentences"],
        })
    return lines


def material_lines(corpus: dict) -> list[str]:
    """选材库里的 B 站正本清单（只暴露，不参与 X 侧去重 / 归栏）。"""
    lines = ["", "## 十、B 站动态正本（只读，第二数据源）", ""]
    rows = corpus.get("bilibili") or []
    lines.append(f"- 当期覆盖日命中 {len(rows)} 条动态；"
                 "键 `bilibili:<动态 id>` 与 X 侧源索引分开放，互不合并。")
    for rec in rows:
        lines.append(
            f"- `{rec['key']}` → {rec['url']}（{rec['publisher']} · "
            f"`{rec['handle']}` · {rec['published_at'] or '时间未知'} · "
            f"{rec['source_file']}）")
    if not rows:
        lines.append("- （本期窗口内没有 B 站动态正本）")
    return lines
