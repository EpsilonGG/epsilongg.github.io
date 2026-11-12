"""筛选层：四套机制按固定顺序执行，产出可核对的记录与证据。

顺序（不可调换）：
  ① 全量源索引 → ② 四类 + 转发提升 → ③ 原推正文层内容去重（留最新，源索引全留）
  → ④ 栏目强制词 / 生日词标注 → ⑤ 非 manufacturer 过筛除池
  → ⑥ 内容驱动三栏归栏（强制词覆盖）→ ⑦ 四层展示结构 + tier_order 排序

`account_class` 只进筛选层，绝不参与 ⑥。每条记录都带 `verdict` 与 `reason`。
"""
from __future__ import annotations

import hashlib
import html
import re
from collections import Counter, defaultdict
from datetime import datetime

from .config import COLUMNS, INDUSTRY, MOVEMENT, NEW, WORK
from . import brackets
from .corpus import TITLE_RE, norm_title
from .identity import Identity
from .titles import TitleNormalizer

# 识别用：比 corpus.TITLE_RE 多认「」，但只认「归一后在语料 titles 里」的那几个，
# 所以「恢复」「前缀：」这类引语不会被当成题名；『』/《》 优先于 「」。
FIND_RE = re.compile(r"([『《「])([^』》」]{1,60})[』》」]")

CLASS_PREFIX = dict(zip(COLUMNS, ("w:", "m:", "i:")))
BRAND_NEWS_GROUP = "品牌动向"


def _norm_text(text: str) -> str:
    return "".join(str(text or "").split())


def _timestamp(value: str) -> str:
    """UTC ISO 字符串；缺失时返回空串（排序时排最后）。"""
    return str(value or "")


def content_groups(refs: dict) -> tuple[dict[str, str], list[dict]]:
    """原推正文归一后完全相同 = 一组。组内按 published_at 留最新展示项。"""
    buckets: dict[str, list[str]] = defaultdict(list)
    for key, ref in refs.items():
        norm = _norm_text(ref.get("text"))
        if norm:
            buckets[norm].append(key)
    key_to_gid: dict[str, str] = {}
    groups: list[dict] = []
    for index, (norm, keys) in enumerate(sorted(buckets.items()), start=1):
        gid = f"cg{index:04d}"
        ordered = sorted(keys, key=lambda k: (_timestamp((refs[k] or {}).get("published_at")), k))
        display = ordered[-1]
        for key in keys:
            key_to_gid[key] = gid
        groups.append({
            "gid": gid, "norm_text": norm[:160], "keys": sorted(keys),
            "display_key": display,
            "display_published_at": _timestamp((refs[display] or {}).get("published_at")),
            "duplicate": len(keys) > 1,
        })
    return key_to_gid, groups


def _records(corpus: dict) -> tuple[list[dict], list[dict]]:
    """记录 = 日报整行（分句索引的 context / 看点 / 互动），works[] 无出处只进素材。"""
    by_context: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for cand in corpus["candidates"]:
        key = (cand["issue"], _norm_text(cand["context"]))
        if key not in by_context:
            by_context[key] = {
                "origin": "clause", "issue": cand["issue"], "day": cand["day"],
                "text": cand["context"], "sources": [], "candidates": [],
                "groups": [], "handles": [],
            }
            order.append(key)
        rec = by_context[key]
        for source in cand.get("sources") or []:
            if source not in rec["sources"]:
                rec["sources"].append(source)
        rec["candidates"].append({
            "clause_id": cand["clause_id"], "text": cand["text"],
            "context": cand["context"], "sources": cand["sources"],
            "day": cand["day"], "precision": cand["precision"],
        })
        if cand["group"] and cand["group"] not in rec["groups"]:
            rec["groups"].append(cand["group"])
        if cand["handle"] and cand["handle"] not in rec["handles"]:
            rec["handles"].append(cand["handle"])

    records = [by_context[k] for k in order]
    prose_only: list[dict] = []
    for row in corpus["daily_rows"]:
        if row["origin"] == "work":
            prose_only.append(row)
            continue
        records.append({
            "origin": row["origin"], "issue": row["issue"], "day": row["day"],
            "text": row["text"], "sources": list(row["sources"]),
            "candidates": [], "groups": [], "handles": [],
        })
    for i, rec in enumerate(records, start=1):
        rec["rid"] = f"r{i:04d}"
        rec["sources"] = sorted(set(rec["sources"]))
    return records, prose_only


def _newest(records: list[dict], refs: dict) -> dict:
    def score(rec: dict) -> tuple:
        times = [_timestamp((refs.get(k) or {}).get("published_at")) for k in rec["sources"]]
        return (rec["day"], max([t for t in times if t] or [""]), rec["rid"])
    return max(records, key=score)


def dedupe_records(records: list[dict], refs: dict, key_to_gid: dict) -> tuple[list[dict], list[dict]]:
    """两道去重：内容组相同留最新；整行文字相同留最新。被并掉的键全部留在源索引。"""
    evidence: list[dict] = []
    alive = list(records)

    for stage, keyfn in (
        ("content_group", lambda r: tuple(sorted({key_to_gid[k] for k in r["sources"]
                                                  if k in key_to_gid}))),
        ("identical_text", lambda r: _norm_text(r["text"])),
    ):
        buckets: dict[object, list[dict]] = defaultdict(list)
        for rec in alive:
            key = keyfn(rec)
            if stage == "content_group" and not key:
                continue
            buckets[key].append(rec)
        kept: list[dict] = []
        for key, group in buckets.items():
            if len(group) == 1:
                kept.append(group[0])
                continue
            winner = _newest(group, refs)
            merged = sorted({k for rec in group for k in rec["sources"]})
            winner["sources"] = merged
            winner["source_index_all"] = merged
            kept.append(winner)
            evidence.append({
                "stage": stage, "key": str(key)[:160], "kept": winner["rid"],
                "dropped": [r["rid"] for r in group if r is not winner],
                "source_keys_all": merged,
                "kept_day": winner["day"],
            })
        # 未参与本道去重的记录原样带回
        if stage == "content_group":
            covered = {r["rid"] for group in buckets.values() for r in group}
            kept.extend(r for r in alive if r["rid"] not in covered)
        alive = kept
    for rec in alive:
        rec.setdefault("source_index_all", sorted(set(rec["sources"])))
    return alive, evidence


def annotate(records: list[dict], rules: dict) -> list[dict]:
    """④ 在筛除池之前标注「栏目强制词」与「生日词」——两者优先于筛除池。

    * 栏目强制词决定归栏，且保证该条不被 drop_if 里的「通販 / 特典 / 抽選」误杀；
    * 生日词只决定「默认不进初稿」：记录仍为 admit（留在筛选页），
      由 decisions.deleted_* 默认勾掉，点「恢复」即可入稿。
    """
    forced = [{"column": str(e.get("column") or ""),
               "patterns": [re.compile(p) for p in (e.get("patterns") or [])]}
              for e in (rules.get("column_forced") or [])]
    birthday = [re.compile(p) for p in
                ((rules.get("birthday") or {}).get("patterns") or [])]
    substantive = [re.compile(p) for p in
                   ((rules.get("substantive") or {}).get("patterns") or [])]
    no_subject = [re.compile(p) for p in
                  ((rules.get("no_subject") or {}).get("patterns") or [])]
    birthday_exempt = bool((rules.get("birthday") or {}).get("exempt_if_substantive"))
    evidence = []
    for rec in records:
        text = rec["text"]
        hit_forced = ""
        for entry in forced:
            if any(p.search(text) for p in entry["patterns"]):
                hit_forced = entry["column"]
                break
        rec["forced_column"] = hit_forced
        # 实质内容：一句话里只要有发售/更新/特典这类硬信息，就不算寒暄。
        rec["substantive"] = any(p.search(text) for p in substantive)
        rec["birthday"] = any(p.search(text) for p in birthday)
        rec["birthday_exempt"] = bool(
            rec["birthday"] and birthday_exempt and rec["substantive"])
        # 无主体观后感：命中空话词且没有实质内容（栏目在 classify 之后才定）。
        rec["no_subject"] = (any(p.search(text) for p in no_subject)
                             and not rec["substantive"])
        if hit_forced or rec["birthday"]:
            evidence.append({"rid": rec["rid"], "forced_column": hit_forced,
                             "birthday": rec["birthday"],
                             "birthday_exempt": rec["birthday_exempt"],
                             "no_subject": rec["no_subject"], "text": text[:160]})
    return evidence


def prefilter(records: list[dict], identity: Identity, rules: dict) -> list[dict]:
    cfg = rules.get("prefilter") or {}
    apply_to = frozenset(cfg.get("apply_to") or ())
    drops = [re.compile(p) for p in (cfg.get("drop_if") or [])]
    keeps = [re.compile(p) for p in (cfg.get("keep_if") or [])]
    evidence = []
    for rec in records:
        info = identity.resolve(rec["sources"], rules["_refs"])
        rec["identity"] = info
        rec["account_class"] = info["class"]
        text = rec["text"]
        # 生日词只有在「没有实质内容」时才压掉这条；庆生＋发售的按正常条目走。
        birthday_only = bool(rec["birthday"] and not rec.get("birthday_exempt"))
        if rec["forced_column"]:
            verdict, reason = ("admit",
                               f"栏目强制词 → {rec['forced_column']}：优先于筛除池"
                               + ("；生日词默认不入初稿" if birthday_only else ""))
        elif birthday_only:
            verdict, reason = "admit", "生日词：留在筛选页、默认不进初稿（可点恢复）"
        elif rec["birthday"]:
            verdict, reason = "admit", "生日词但含实质内容（发售/更新/特典等）：照常入稿"
        elif not rec["sources"]:
            verdict, reason = "review", "no_source：日报正本整行无出处键，留待人工"
        elif info["class"] not in apply_to:
            verdict, reason = "admit", f"{info['class']} 不过筛除池"
        else:
            hit_drop = [p.pattern for p in drops if p.search(text)]
            hit_keep = [p.pattern for p in keeps if p.search(text)]
            if hit_drop and not hit_keep:
                verdict, reason = "drop", "宣传/广告词：" + ", ".join(hit_drop[:3])
            elif hit_keep:
                verdict, reason = "admit", "业界级信号：" + ", ".join(hit_keep[:3])
            else:
                verdict, reason = "review", "非 manufacturer 且两表都未命中，进候选池待人工"
        rec["verdict"], rec["verdict_reason"] = verdict, reason
        evidence.append({"rid": rec["rid"], "class": info["class"],
                         "promoted": info["promoted"], "verdict": verdict,
                         "reason": reason, "sources": rec["sources"],
                         "forced_column": rec["forced_column"],
                         "birthday": rec["birthday"]})
    return evidence


def classify(records: list[dict], corpus: dict, identity: Identity, rules: dict,
             normalizer: TitleNormalizer) -> None:
    """归栏只看内容：账号类不参与；栏目强制词在最后覆盖，并留原始判定。"""
    titles = set(corpus["titles"])
    refs = rules["_refs"]
    ops = [re.compile(p) for p in ((rules.get("movement_rules") or {}).get("patterns") or [])]
    signals = [str(s) for s in ((rules.get("movement_rules") or {}).get("signals") or []) if s]
    brand_vocab = sorted(
        {str(x) for x in (rules.get("extra_brands") or [])}
        | {str(x) for group in (rules.get("tiers") or {}).values() for x in group},
        key=lambda s: -len(s),
    )
    yield_cfg = rules.get("column_forced_yield") or {}
    yield_sig = ([re.compile(p) for p in (yield_cfg.get("signals") or [])]
                 if yield_cfg.get("enabled") else [])
    forced_patterns = {str(e.get("column") or ""):
                       [re.compile(p) for p in (e.get("patterns") or [])]
                       for e in (rules.get("column_forced") or [])}
    bare_cfg = rules.get("bare_title") or {}
    bare_min = int(bare_cfg.get("min_len") or 4)
    bare_sig = [re.compile(p) for p in (bare_cfg.get("signals") or [])]
    bare_skip = [re.compile(p) for p in (bare_cfg.get("skip_if") or [])]
    # 裸题名兜底用：把作品名与正文都去掉空白再比，避免「题名带空格、正文不带」漏配。
    norm_titles = sorted(((t, _norm_text(t)) for t in titles if len(_norm_text(t)) >= bare_min),
                         key=lambda x: -len(x[1]))
    for rec in records:
        text = rec["text"]
        found = [(m.group(1), norm_title(m.group(2))) for m in FIND_RE.finditer(text)]
        # 『』/《》 是明确的题名号，优先；「」 只作兜底——它也可能是角色名或引语。
        strict = [t for opener, t in found if opener in "『《" and t in titles and len(t) >= 2]
        loose = [t for _, t in found if t in titles and len(t) >= 2]
        work = (strict or loose or [""])[0]
        work_basis = "text" if work else ""
        if not work and bare_cfg.get("enabled"):
            # 正文没给作品名加书名号时的兜底（2026-11-10 用户裁决：
            # 「包装版」就是实体版游戏，这条本来就该算作品情报）。只在句子里
            # 有「实体版 / 装盘 / 发售」这类作品发售信号时才认，取最长命中。
            has_release = any(p.search(text) for p in bare_sig)
            digest = any(p.search(text) for p in bare_skip)
            if not digest and (has_release or not bare_cfg.get("require_substantive")):
                normed = _norm_text(text)
                hit = next((t for t, n in norm_titles if n and n in normed), "")
                if hit:
                    work, work_basis = hit, "bare+release"
        if not work:
            # group 只在「作品名在 titles 里」且「某条原推原文逐字出现它」时才采信。
            for group in rec.get("groups") or []:
                if str(group).startswith("@"):
                    continue
                candidate = norm_title(group)
                if candidate not in titles or len(candidate) < 2:
                    continue
                if any(candidate in _norm_text((refs.get(k) or {}).get("text") or "")
                       for k in rec["sources"]):
                    work, work_basis = candidate, "group+verbatim"
                    break
        account_ops = any(p.search(text) for p in ops)
        signal_hit = next((s for s in signals if s in text), "")
        brand = rec["identity"]["brand"]
        if not brand:
            brand = next((b for b in brand_vocab if b and b in text), "")
            brand = identity.canonical_brand(brand)
        if work and not account_ops:
            base_column = WORK
        elif work and account_ops:
            base_column = MOVEMENT
        elif brand or signal_hit:
            base_column = MOVEMENT
        else:
            base_column = INDUSTRY
        column = rec["forced_column"] or base_column
        # 强制词让位：作品发售信号比强制词先出现时，听作品的（谁先出现听谁）。
        yielded = False
        if (yield_sig and rec["forced_column"]
                and rec["forced_column"] == yield_cfg.get("when_forced_column")
                and base_column == yield_cfg.get("require_base_column")
                and (work or not yield_cfg.get("require_work"))):
            pats = forced_patterns.get(rec["forced_column"]) or []
            forced_pos = min((m.start() for p in pats
                              for m in [p.search(text)] if m), default=-1)
            sig_pos = min((m.start() for p in yield_sig
                           for m in [p.search(text)] if m), default=-1)
            if forced_pos >= 0 and sig_pos >= 0 and sig_pos < forced_pos:
                column = base_column
                yielded = True
        canonical = normalizer.canonical(work) if work else ""
        # 书名号归一（2026-11-10 裁决）：作品『』/ 角色「」/ 乐曲书籍《》。
        # 放在归栏之后做，作品名识别仍用原文本，避免先改括号再影响匹配。
        text_fixed, br_changes = brackets.normalize(rec["text"], titles,
                                                    rules.get("brackets") or {})
        rec.update({
            "work": work, "work_basis": work_basis, "column": column,
            "column_base": base_column, "work_canonical": canonical,
            "brand": brand or "未标注品牌", "account_ops": account_ops,
            "signal": signal_hit, "forced_yielded": yielded,
            "text": text_fixed, "bracket_changes": br_changes,
            "classify_reason": (
                f"work={work or '-'}({work_basis or 'none'}) ops={account_ops} "
                f"signal={signal_hit or '-'} brand={brand or '-'} → {base_column}"
                + ("；强制词让位（发售信号更靠前）→ " + column if yielded
                   else ("；强制词覆盖 → " + column if rec["forced_column"] else ""))
            ),
        })


def _subject(identity: Identity, refs: dict, rec: dict) -> str:
    """主语＝发布账号显示名；manufacturer 转发的条目显示「被转发者（原作者）」的显示名。"""
    names = identity.names
    if rec["identity"]["promoted"]:
        origins = []
        for key in rec["source_index_all"]:
            eff = identity.effective_handle(key, refs)
            if not eff["promoted"]:
                continue
            name = names.get(eff["origin"], "")
            if not name:
                name = "@" + eff["origin"] if eff["origin"] else ""
            if name and name not in origins:
                origins.append(name)
        subject = "、".join(origins[:2])
    else:
        subject = rec["identity"]["display_name"] or ""
    if subject and subject in rec["text"]:
        return ""
    return subject


def _display_title(title: str) -> str:
    """展示用小标题：成对半角 `~` 在 Markdown 里会渲染成 <del>（删除线）。

    只在展示层给每个 `~` 两侧补空格，把配对拆开；归并键 group_key /
    work_canonical 仍用原始归一名，合并不受影响。
    """
    if "~" not in str(title or ""):
        return str(title or "")
    return " ".join(str(title).replace("~", " ~ ").split())


def _unescape(text: str) -> str:
    """把数据源里的 HTML 实体还原成字面字符。

    `src/config/daily-roster-galgame.json` 里 F&C 的 `name` 存的是
    `F&amp;C／エフアンドシー`（名单是从 HTML 抓来的，抓取时没做反转义），
    于是正文里出现 `### F&amp;C` —— Markdown 不认这个实体，读者看到的是
    「F&amp;C」。名单本身归日报所有、改动要过保护集，所以在周报这一层还原。
    """
    return html.unescape(str(text or ""))


def _profile_url(handle: str) -> str:
    """账号主页链接。只由 handle 拼 `x.com/<handle>`，不涉及推文 ID。"""
    handle = str(handle or "").strip()
    return "https://x.com/" + handle if handle else ""


def _brand_account(items: list[dict]) -> str:
    """这一栏里该品牌的官号 handle；没有官号条目就返回空串。

    判据是「条目来自 manufacturer 账号」，不区分原创还是转发——品牌号转发
    也是这个官号在发消息，中标题一样该能点进去。频次最高者优先，同频取先出现的。
    """
    counter: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for idx, item in enumerate(items):
        if item.get("account_class") != "manufacturer":
            continue
        for src in item.get("sources") or []:
            if src.get("class") != "manufacturer" or not src.get("handle"):
                continue
            handle = str(src["handle"])
            counter[handle] += 1
            first_seen.setdefault(handle, idx)
    if not counter:
        return ""
    return min(counter, key=lambda h: (-counter[h], first_seen[h]))


_URL_HANDLE = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status", re.I)


def _src_url(handle: str, sources: list[dict], link_all: bool = False) -> str:
    """账号 → 该账号名下的推文 URL；查不到返回空串，绝不拼造。

    nitter/rss 只给转发者名下那一条 URL，被转发者自己没有 URL 可挂；
    `link_all` 时把这条 URL 让给被转发者，因为它就是这条内容的实际出处。
    """
    handle = str(handle or "").lower()
    for src in sources:
        u = str(src.get("url") or "")
        match = _URL_HANDLE.search(u)
        if match and u and match.group(1).lower() == handle:
            return u
    for src in sources:
        u = str(src.get("url") or "")
        author = str(src.get("author") or "").lstrip("@").strip().lower()
        if u and author == handle:
            return u
    if link_all:
        for src in sources:
            u = str(src.get("url") or "")
            if u and str(src.get("origin") or "").lower() == handle:
                return u
    return ""


def _src_name(handle: str, sources: list[dict]) -> str:
    """账号 → 名单里的真实显示名（转发者与被转发者都查）；查不到返回空串。"""
    handle = str(handle or "").lower()
    for src in sources:
        if str(src.get("handle") or "").lower() == handle:
            name = str(src.get("display_name") or "")
            if name:
                return name
    for src in sources:
        if str(src.get("origin") or "").lower() == handle:
            name = str(src.get("origin_display_name") or "")
            if name:
                return name
    return ""


def _cased_handle(handle: str, sources: list[dict]) -> str:
    """把（内部一律小写的）handle 还原成原始大小写，只用于显示。

    X 的 handle 显示区分大小写：真实账号是 `AirVelo2026`，而名单与源索引里存的
    是小写 `airvelo2026`（匹配必须不区分大小写）。原始大小写只有两处拿得到：
    推文 URL 的路径段、以及 `author` 本身就是干净 handle 的时候。
    都拿不到就用传进来的写法——绝不靠猜。
    """
    low = str(handle or "").strip().lower()
    if not low:
        return ""
    for src in sources:
        match = _URL_HANDLE.search(str(src.get("url") or ""))
        if match and match.group(1).lower() == low:
            return match.group(1)
    for src in sources:
        author = str(src.get("author") or "").lstrip("@").strip()
        if author and author.lower() == low:
            return author
    return str(handle or "")


def _linkify_subject(text: str, sources: list[dict], rules: dict) -> str:
    """转推条目把正文里已写出的原作者名挂上原推链接。

    只在「没有前缀」时用（有前缀时前缀已经挂过链接）：模型把账号名写进了
    句子（「转 Moepedia 的…」），就不再加前缀，避免同一账号写两遍；改成把
    那个名字原地变成 `[Moepedia](url)`，可见文字一字不变，只是多了链接。
    要求名字在句子里恰好出现一次，且句子里还没有任何链接，否则原样返回。
    """
    cfg = rules.get("off_roster_links") or {}
    if not cfg.get("enabled", True):
        return text
    body = str(text or "")
    if not body or "](" in body:
        return body
    for src in sources:
        if not src.get("promoted"):
            continue
        handle = str(src.get("origin") or "").lower()
        if not handle:
            continue
        url = _src_url(handle, sources, link_all=True)
        if not url:
            continue
        label = _src_name(handle, sources) or _cased_handle(handle, sources)
        if body.count(label) != 1:
            continue
        return body.replace(label, "[" + label + "](" + url + ")", 1)
    return body


def _prefix_md(prefix: str, sources: list[dict], rules: dict,
               link_all: bool = False) -> str:
    """账号前缀 → `[显示名](原推 URL)`。

    * `link_all=True`（品牌号转发的条目）：主语无论是否在名单里都做链接，
      显示名优先用名单里的真实名称，查不到才退回不带 `@` 的 handle。
    * `link_all=False`：只有名单外账号（前缀以 `@` 开头）才做链接，其余原样保留。
    URL 只从 `source_refs.url` 里按 URL 中的 handle 精确匹配取（再以 author
    精确匹配兜底），查不到就退回纯文本，绝不拼造链接、绝不用子串猜。
    """
    cfg = rules.get("off_roster_links") or {}
    prefix = str(prefix or "")
    if not cfg.get("enabled", True) or not prefix:
        return prefix
    style = str(cfg.get("handle_style") or "name")

    def handle_of(part: str) -> str:
        if part.startswith("@"):
            return part[1:].strip().lower()
        if not link_all:
            return ""
        # 主语已经是显示名：反查 handle，转推一样要挂链接。
        for src in sources:
            if str(src.get("display_name") or "") == part:
                return str(src.get("handle") or "").lower()
        for src in sources:
            if str(src.get("origin_display_name") or "") == part:
                return str(src.get("origin") or "").lower()
        return ""

    parts: list[str] = []
    for part in prefix.split("、"):
        handle = handle_of(part)
        if not handle:
            parts.append(part)
            continue
        url = _src_url(handle, sources, link_all)
        # 匹配用小写，显示用原始大小写（`@AirVelo2026` 而不是 `@airvelo2026`）。
        shown = _cased_handle(handle, sources)
        if style == "at_slashed":
            label = "@//" + shown + "/"
        elif style == "at_handle":
            label = "@" + shown
        else:
            # name：名单里的真实名称优先；查不到（名单外账号）退回 `@handle`。
            # 2026-11-10 用户裁决：标签就是 `@AirVelo2026` 这个形态——**不带双斜杠**
            # （旧写法 `@//AirVelo2026/` 已废弃），但一样挂原推超链接。
            label = _src_name(handle, sources) or ("@" + shown)
        parts.append("[" + label + "](" + url + ")" if url else label)
    return "、".join(parts)


def build_sections(records: list[dict], corpus: dict, identity: Identity,
                   rules: dict, normalizer: TitleNormalizer) -> list[dict]:
    """四层展示：栏目(大) → 品牌(中) → 游戏(小) → `- ` 文本(条目)。

    review / drop 不进初稿，只留在筛选页与素材库；生日词条目 admit 但默认勾删。
    """
    refs = rules["_refs"]
    excl_cfg = rules.get("default_excluded") or {}
    exclusions = set(excl_cfg.get("group_labels") or [])
    excl_brands = set(excl_cfg.get("brands") or [])
    excl_columns = set(excl_cfg.get("columns") or [])
    no_subject_cols = set((rules.get("no_subject") or {}).get("apply_to") or ())
    grouped: dict[tuple[str, str], dict] = {}
    for rec in records:
        column = rec["column"]
        if column == INDUSTRY:
            label = _unescape(rec["identity"]["display_name"]) or (
                "@" + (rec["identity"]["handles"][0] if rec["identity"]["handles"] else "名单外账号"))
        else:
            # 名单里的品牌名带 HTML 实体（`F&amp;C`），展示前还原成 `F&C`。
            label = _unescape(rec["brand"])
        key = (column, label)
        section = grouped.setdefault(key, {
            "key": CLASS_PREFIX[column] + label, "label": label,
            "column": column,
            "type": dict(zip(COLUMNS, ("brand", "movement", "industry")))[column],
            "items": [],
        })
        canonical = rec["work_canonical"]
        # 合并栏（2026-11-10 正式版）：品牌动向并入作品情报后，没有作品的品牌级条目
        # 不能再叫「未标注作品」——那会被默认排除掉。给它们一个自己的组名，
        # 组内仍是「一条一句」，不参与作品名归并。
        if canonical:
            group_label = f"『{_display_title(canonical)}』"
        elif column == MOVEMENT:
            group_label = BRAND_NEWS_GROUP
        else:
            group_label = "未标注作品"
        group_key = "g:" + hashlib.md5(
            (section["key"] + "|" + normalizer.canonical_norm(canonical)).encode("utf-8")
        ).hexdigest()[:12]
        source_records = []
        for source_key in rec["source_index_all"]:
            ref = refs.get(source_key) or {}
            eff = identity.effective_handle(source_key, refs)
            source_records.append({
                "key": source_key, "url": ref.get("url") or "",
                "text": ref.get("text") or "", "author": ref.get("author") or "",
                "handle": eff["handle"],
                "display_name": _unescape(identity.names.get(eff["handle"], "")),
                # 转推条目：被转发者（原作者）的 handle 与显示名也要带上，
                # 否则主语写成原作者显示名后，链接反查不到账号、只能退成纯文本。
                "origin": eff["origin"],
                "origin_display_name": _unescape(identity.names.get(eff["origin"], "")),
                "retweet": eff["retweet"],
                "mapped": eff["in_roster"], "class": eff["class"],
                "promoted": eff["promoted"],
                "published_at": ref.get("published_at") or "",
            })
        accounts = []
        for src in source_records:
            # 名单外的账号没有显示名，退回 handle —— 但要用原始大小写，
            # 否则筛选页会把 `@AirVelo2026` 印成 `@airvelo2026`。
            name = src["display_name"] or (
                "@" + _cased_handle(src["handle"], [src]) if src["handle"] else "名单外账号")
            entry = {"name": name, "mapped": src["mapped"], "class": src["class"]}
            if entry not in accounts:
                accounts.append(entry)
        # 官号判定：品牌官号自己发的才算「官号条目」。
        # manufacturer 转发（转发提升）的推文，实际发布者是原作者，按上一轮裁决
        # 主语仍写原作者，因此这里一律算非官号，保留「@handle：」的格式。
        is_official = (rec["account_class"] == "manufacturer"
                       and not any(src["promoted"] for src in source_records))
        subject = _subject(identity, refs, rec)
        reasons = []
        if rec["birthday"] and not rec.get("birthday_exempt"):
            reasons.append("生日词")
        if group_label in exclusions and (not excl_columns or column in excl_columns):
            reasons.append("未标注作品")
        if label in excl_brands and (not excl_columns or column in excl_columns):
            reasons.append("未标注品牌")
        if (rec.get("no_subject") and (not no_subject_cols or column in no_subject_cols)):
            reasons.append("无主体观后感")
        digest = hashlib.md5(_norm_text(rec["text"]).encode("utf-8")).hexdigest()[:8]
        prefix_md = _prefix_md(subject, source_records, rules,
                               link_all=bool(rec["identity"]["promoted"]))
        # 转推但主语已写进正文（没前缀）时，把那个名字原地挂上原推链接。
        sentence_md = (rec["text"] if prefix_md
                       else _linkify_subject(rec["text"], source_records, rules))
        section["items"].append({
            "key": section["key"] + "::" + rec["day"] + "::" + digest,
            "label": group_label, "sentence": rec["text"],
            "sentence_md": sentence_md,
            "group_key": group_key, "group_label": group_label,
            "subject_prefix": subject,
            "prefix_md": prefix_md,
            "is_official": is_official,
            "retweeted": bool(rec["identity"]["promoted"]),
            "retweet": any(e.get("retweet") for e in rec["identity"].get("evidence") or []),
            "default_deleted": bool(reasons),
            "default_reason": " · ".join(reasons),
            "birthday": bool(rec["birthday"]),
            "birthday_exempt": bool(rec.get("birthday_exempt")),
            "no_subject": bool(rec.get("no_subject")),
            "forced_column": rec["forced_column"],
            "column_base": rec["column_base"],
            "draft": True, "day": rec["day"], "days": [rec["day"]],
            "origin": rec["origin"], "verdict": rec["verdict"],
            "account_class": rec["account_class"], "classify_reason": rec["classify_reason"],
            "work": rec["work"], "work_canonical": canonical,
            "work_basis": rec["work_basis"],
            "sources": source_records,
            "candidates": rec["candidates"],
            "accounts": accounts,
            "lines": [], "line_subjects": [], "statements_dropped": 0,
            "_group_sort": normalizer.rank(canonical) if canonical else ("", ""),
        })

    sections = []
    for (column, label), section in grouped.items():
        section["items"].sort(key=lambda i: (i["_group_sort"],
                                             0 if i["is_official"] else 1,
                                             i["day"], i["key"]))
        for item in section["items"]:
            del item["_group_sort"]
        items = section["items"]
        # 品牌中标题要不要挂官号链接：看这一栏里这个品牌有没有「官号自己发/转」的条目。
        # 取该品牌在这一栏出现最多的 manufacturer handle（同品牌多号时按频次定），
        # 只拼 `x.com/<handle>` 主页链接，不涉及推文 ID，所以不会拼造出处。
        section["brand_handle"] = _brand_account(items)
        section["brand_url"] = _profile_url(section["brand_handle"])
        # 三档梯队：作品情报与品牌动向共用同一套排序；业界动向按条目数降序。
        section["rank"] = (identity.unit_rank(label, len(items), label)
                           if column != INDUSTRY else (0, 0, -len(items), label))
        section["groups"] = [
            {"key": g, "label": next(i["group_label"] for i in items if i["group_key"] == g),
             "items": [i["key"] for i in items if i["group_key"] == g]}
            for g in dict.fromkeys(i["group_key"] for i in items)
        ]
        sections.append(section)
    sections.sort(key=section_sort_key)
    apply_display_columns(sections, rules)
    return sections


def section_sort_key(section: dict) -> tuple:
    """品牌大单元的默认顺序（2026-11-12 用户裁决）。

    旧写法先按归栏三值分组（作品情报 → 品牌动向 → 业界动向），同一栏内再按
    rank 排。结果「新作」栏（只有作品情报派生的大单元）是纯梯队序，而「作品情报」
    栏里由品牌动向合并进来的大单元被整段压到末尾——梯队 1 的 Key / ぱれっと
    会排在一堆梯队 3 品牌之后，两栏看起来用了两套排序。

    现在两栏共用同一份 rank：归栏三值不再参与比较，作品情报与品牌动向派生的
    大单元按 (梯队 → 梯队内顺序 → 条目数降序 → 名称) 混排，业界动向单独垫底。
    新作栏全由作品情报派生，相对顺序不变；改的只是作品情报栏的品牌顺序。
    `decisions.section_order` 直接取这份顺序，出稿 / 筛选页 JS 都不用另算。
    """
    return (section["column"] == INDUSTRY, section["rank"], section["label"])


def apply_display_columns(sections: list[dict], rules: dict) -> set[str]:
    """给每条打上展示栏目（2026-11-10 正式版）：品牌动向并入作品情报，新作整组上提。

    归栏三值不动——那是「为什么放这里」的证据；展示只做两件事：
    品牌动向 → 作品情报（合并），作品情报里带新作标签的游戏 → 第一栏「新作」。
    新作标签由 game_routing 的游戏级信号算出（与分流预览同一份口径）。
    结果写进 `item["display_column"]`，出稿与筛选页都读它，避免两端各算一遍。
    """
    from .game_routing import new_work_labels

    labels = new_work_labels(sections, rules.get("game_routing") or {})
    for section in sections:
        base = WORK if section["column"] == MOVEMENT else section["column"]
        for item in section["items"]:
            column = base
            if base == WORK and item["group_label"] in labels:
                column = NEW
            item["display_column"] = column
            item["new_work"] = column == NEW
    return labels


def run(corpus: dict, rules: dict) -> dict:
    refs = corpus["source_refs"]
    rules = dict(rules)
    rules["_refs"] = refs
    identity = Identity(rules)
    normalizer = TitleNormalizer(corpus["titles"], rules)
    key_to_gid, groups = content_groups(refs)
    raw, prose_only = _records(corpus)
    deduped, dedupe_evidence = dedupe_records(raw, refs, key_to_gid)
    annotation = annotate(deduped, rules)
    filter_evidence = prefilter(deduped, identity, rules)
    classify(deduped, corpus, identity, rules, normalizer)
    admitted = [r for r in deduped if r["verdict"] == "admit"]
    # 逐字取自日报的看点 / 互动走筛选页的专用行块（按钮规格与旧稿一致），
    # 但仍按内容归到三组之一；分句索引派生的整行走品牌大单元。
    section_records = [r for r in admitted if r["origin"] == "clause"]
    feeds = [r for r in admitted if r["origin"] in ("highlight", "interaction")]
    sections = build_sections(section_records, corpus, identity, rules, normalizer)
    return {
        "corpus": corpus, "rules_snapshot": {k: v for k, v in rules.items() if k != "_refs"},
        "identity": identity, "normalizer": normalizer,
        "content_groups": groups, "key_to_gid": key_to_gid,
        "records": deduped, "prose_only": prose_only,
        "sections": sections, "feeds": feeds,
        "evidence": {
            "dedupe": dedupe_evidence,
            "prefilter": filter_evidence,
            "annotation": annotation,
            "title_groups": normalizer.evidence(),
            "content_groups_duplicated": [g for g in groups if g["duplicate"]],
            "classification": [
                {"rid": r["rid"], "column": r["column"], "column_base": r["column_base"],
                 "forced_column": r["forced_column"], "birthday": r["birthday"],
                "forced_yielded": bool(r.get("forced_yielded")),
                "birthday_exempt": bool(r.get("birthday_exempt")),
                "substantive": bool(r.get("substantive")),
                "no_subject": bool(r.get("no_subject")),
                 "work": r["work"], "work_canonical": r["work_canonical"],
                 "brand": r["brand"], "class": r["account_class"],
                 "verdict": r["verdict"], "reason": r["classify_reason"]}
                for r in deduped
            ],
            "promotions": [
                {"rid": r["rid"], "handles": r["identity"]["handles"],
                 "class": r["account_class"], "class_source": r["identity"]["class_source"]}
                for r in deduped if r["identity"]["promoted"]
            ],
        },
        "stats": {
            "raw_records": len(raw), "after_dedupe": len(deduped),
            "prose_only_rows": len(prose_only),
            "verdicts": {v: sum(1 for r in deduped if r["verdict"] == v)
                         for v in ("admit", "review", "drop")},
            "classes": {c: sum(1 for r in deduped if r["account_class"] == c)
                        for c in ("manufacturer", "creator", "info", "other")},
            "columns": {c: sum(1 for r in admitted if r["column"] == c)
                        for c in COLUMNS},
            "feed_items": len(feeds),
            "content_groups": len(groups),
            "duplicate_groups": sum(1 for g in groups if g["duplicate"]),
            "promoted_records": sum(1 for r in deduped if r["identity"]["promoted"]),
            "sections": len(sections),
            "items": sum(len(s["items"]) for s in sections),
            "game_groups": sum(len(s["groups"]) for s in sections),
            "title_merges": len(normalizer.evidence()["merges"]),
            "birthday_records": sum(1 for r in deduped if r["birthday"]),
            "birthday_hidden": sum(1 for r in deduped
                                   if r["birthday"] and not r.get("birthday_exempt")),
            "birthday_exempt": sum(1 for r in deduped if r.get("birthday_exempt")),
            "no_subject_records": sum(1 for r in deduped if r.get("no_subject")),
            "forced_yielded": sum(1 for r in deduped if r.get("forced_yielded")),
            "forced_records": sum(1 for r in deduped if r["forced_column"]),
        },
    }
