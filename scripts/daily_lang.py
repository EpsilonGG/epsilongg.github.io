"""中文日报的「语言闸门」：拦下整篇漂成日文的模型回答。

2026-11-05 的 261105 / 261105-g，以及更早的 261030-g，都出现过同一种事故：
题面是中文、材料（X 推文）全是日文，模型顺着材料把 `summary` / `highlights` /
`works` / `people[].summary` 全写成了日文；`apply` 照单全收，`confirm` 和
`publish` 也看不出异常，最后整页中文日报变成日文。

光在题面补一句「请用简体中文」不够——提示词会漂移，必须有**判卷级别**的机械检查。
这个模块就是那道检查，两处调用：

* `daily/validate.py::validate_answer()` —— 回答落盘前拦下（不进正本）。
* `scripts/check_daily_site.py::check()` —— 已发布的正本再扫一遍（历史数据也兜住）。

判定不是「有没有假名」：站内中文稿本来就大量保留日文人名（柚木つばめ）、
作品名（『ワンナイトアフター』）与品牌名，用假名数量会大面积误杀。
这里数的是**日语语法信号**（助词、谓语词尾、日文新字体、被引号剥开后落在
行首的助词）与**中文独有标记**（的/了/在/并/将 + 发售/公开/参演…），
两者同时成立才判日文：

    日文信号 ≥ 2 且 中文标记 == 0  →  判为日文

引号里的作品名/曲名先剥掉，避免把标题里的假名算成语法；剥的时候按**成对的外层
括号**走，否则 `『【A.S.】天才を突き動かすもの』` 里的内层 `【】` 会把日文语法
漏出来误杀。中文标记只收**简体中文独有**的字词——`出演`／`新作`／`同日` 这类
中日同形的词不能当证据，否则日文句子会因它们而漏检。

口径在真实语料上标过：291 句已确认的日文事故文案 + 1774 句干净的中文正本文案，
单句召回 90.4%（263/291）、误报 0；**按整份回答/整期正本判**（命中任意一句即
整份作废），三期事故分别命中 89 / 102 / 72 句，召回 100%。只查「人写给人看」的文案字段，不查 handle / URL /
sources / 时间戳。
"""
from __future__ import annotations

import re
from typing import Any, Iterable

# 作品名、曲名、活动名：整段剥掉，里面的假名与日文汉字都不算证据。
# 必须按「成对的外层括号」匹配：`[^』]*` 允许内层 `【】`／`［］` 存在，
# 否则 `『【A.S.】天才を…』` 会先被 `【…】` 截断，日文标题里的助词就漏出来了。
_QUOTED = re.compile(
    r"『[^』]{0,120}』|「[^」]{0,120}」|《[^》]{0,120}》"
    r"|〈[^〉]{0,120}〉|【[^】]{0,120}】|［[^］]{0,120}］"
)
_LATIN = re.compile(r"[A-Za-z0-9_./:%+\-]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")

# 日语助词：前面必须接汉字或片假名，缩小到「语法上的助词」而不是人名里的假名。
_PARTICLE = re.compile(r"[\u4e00-\u9fff\u30a0-\u30ff][がをのにではともからへ]")
# 日语谓语/词尾。这些都是假名串，中文文案里不会出现。
_PREDICATE = re.compile(
    r"ました|です|します|している|している|された|されて|になり|となり|"
    r"について|によって|において|ください|ありがとう|いただき|"
    r"し、|した|する|である|ます|だった|ました|ください|そうです"
)
# 日文新字体 / 和制汉字。中文（简体）稿里不该出现；作品名已先剥掉。
_SHINJITAI = re.compile(r"[発売収覚伝価変対応専従総続録験検済類権実広囲気]")

# 日文助词被作品名剥开后会落在空格/行首，仍是语法信号（例：`『…』が発売`）。
_FREE_PARTICLE = re.compile(r"(?:(?<=[\s　）)］】」』])|^)[がをのにではともからへや](?![ぁ-ん])")

# 中文独有标记：日文不用的虚词 + **简体中文才有**的词。
# `出演`／`新作`／`同日`／`当日`／`加入`／`投稿`／`更新` 这类中日同形词一律
# 不收——它们出现在日文句子里会把「中文标记」点亮，反而让事故稿漏检。
_ZH_MARKER = re.compile(
    r"[的了在并与将把被还也就均已于从到向对及等且或但而则让给这那]"
    r"|公布|发布|发售|公开|宣布|参演|推出|确定|预告|举办|"
    r"收录|上线|开卖|售价|折扣|版本|动态|饰演|"
    r"负责|转发|回复|纪念|活动|直播|发行|上市|开售|完结|"
    r"完工|装盘|汉化|简体|繁体|中文|动画化|体验版|下载版|优惠|"
    r"销量|累计|全球|首日"
)

# 命中一个「日语语法信号」就记 1 分；同一类重复出现按次数累计，但上限 6。
_SCORE_CAP = 6
_JP_THRESHOLD = 2


def _strip(text: str) -> str:
    """剥掉作品名/曲名与拉丁文，只留下要判断语法的部分。"""
    return _LATIN.sub(" ", _QUOTED.sub(" ", text))


def scores(text: str) -> tuple[int, int]:
    """返回 `(日语信号, 中文标记)`。两个数字都只用于判定，不对外当质量分。"""
    body = _strip(text)
    jp = (
        len(_PARTICLE.findall(body))
        + len(_PREDICATE.findall(body))
        + len(_SHINJITAI.findall(body))
        + len(_FREE_PARTICLE.findall(body))
    )
    return min(jp, _SCORE_CAP), min(len(_ZH_MARKER.findall(body)), _SCORE_CAP)


def is_japanese(text: str) -> bool:
    """这句是不是日文叙述（而不是「中文里夹了日文专有名词」）。"""
    if not isinstance(text, str) or not text.strip():
        return False
    if not _CJK.search(text) and not _PARTICLE.search(text):
        return False
    jp, zh = scores(text)
    return jp >= _JP_THRESHOLD and zh == 0


def iter_prose(payload: Any, prefix: str = "$") -> Iterable[tuple[str, str]]:
    """摊平答案/正本里「人写给人看」的文案，跳过 handle / sources / 时间等。

    两种形状都认：`highlights` / `interactions` 的元素可以是 `{"text": …}`，
    也可以是裸字符串；`works` 两种都收。
    """
    if isinstance(payload, str):
        if payload.strip():
            yield prefix, payload
        return
    if isinstance(payload, list):
        for i, item in enumerate(payload):
            path = f"{prefix}[{i}]"
            if isinstance(item, str):
                if item.strip():
                    yield path, item
            elif isinstance(item, dict):
                yield from iter_prose(item, path)
        return
    if not isinstance(payload, dict):
        return

    for key in ("summary", "description", "text", "hook", "description_zh"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            yield f"{prefix}.{key}", value

    for key in ("highlights", "interactions", "insights", "works", "people"):
        value = payload.get(key)
        if isinstance(value, str):
            if value.strip():
                yield f"{prefix}.{key}", value
        elif isinstance(value, list):
            for i, item in enumerate(value):
                path = f"{prefix}.{key}[{i}]"
                if isinstance(item, str):
                    if item.strip():
                        yield path, item
                elif isinstance(item, dict):
                    yield from iter_prose(item, path)


# 中文正本要扫的字段（`hook` / `description_zh` 只存在于日语版，不在正本里）。
REPORT_FIELDS = ("description", "highlights", "works", "interactions", "people")
# 回答里要扫的字段（日语版答案不在这里判：它本来就该是日文）。
ANSWER_FIELDS = ("summary", "highlights", "works", "interactions", "people", "insights")


def scan(payload: dict, fields: Iterable[str] = ANSWER_FIELDS) -> list[tuple[str, str]]:
    """返回所有被判成日文的 `(字段路径, 原文)`，按字段顺序稳定排列。"""
    found: list[tuple[str, str]] = []
    for field in fields:
        for path, text in iter_prose(payload.get(field), f"$.{field}"):
            if is_japanese(text):
                found.append((path, text))
    return found


def scan_answer(answer: dict) -> list[tuple[str, str]]:
    return scan(answer, ANSWER_FIELDS)


def scan_report(report: dict) -> list[tuple[str, str]]:
    return scan(report, REPORT_FIELDS)
