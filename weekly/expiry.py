"""过期贩售：成形时已经结束的促销 / 受注 / 预约消息，整条不进周报。

2026-11-21 用户裁决（原先只做在 B 站行上，2026-11-22 提到周报级）：
「贩卖消息在周报开始形成若已过期（即贩卖结束）则删去那条贩卖信息。」

判据只认**写明结束日**的：

* 结束日必须与「截止 / 为止 / まで / 至 / 到 / 结束」连在一起，不能只是正文里
  随便出现一个日期——B 站与 X 的正文里到处是发售日、开播日、活动日。
* 同一句里必须还有贩售词（セール / 促销 / 受注 / 通贩 / 预约 / 折扣 …），
  否则那是「11/16 发售」这类消息，不是贩售截止。
* 没有结束日的常驻通贩 / 在售消息**不猜**：无法证明已结束就不能删。

三种不被删的情形（都会留下理由，便于复核）：

1. **结果通报**：`为11月9日截止的活动完成抽奖，已通知中奖者` —— 期限已过，但这条
   消息讲的是结果，不是还在卖的贩售信息。
2. **另有一句带未来发售**：同一句里出现未来发售日只是「某作的特典提醒」，
   仍算过期；只有当**另一句**（不含过期日期的那句）写了未来发售 / 定档时，
   删掉会连带丢掉新闻，才保留。
3. 日期本身在未来（`到 25 日`、`受注到 12/1`）——当然不删。

月份解析以「该条自己发生的那天」为锚：只写 `9日` 时按锚日推最近的那一天，
只写 `11/16` 时按锚年补年。锚日缺失才退回成形日。
"""
from __future__ import annotations

import re
from datetime import date, timedelta

# 贩售词：出现这些词才可能是「贩售消息」。
SALE_WORDS = re.compile(
    r"セール|SALE|sale|促销|特卖|特賣|打折|折扣|优惠|優惠|受注|通販|通贩|贩售|販売|贩卖|售卖"
    r"|限时|闪购|閃購|特价|特價|首发折|予約|预约|抽選|抽选|特典|发售特价|応援|应援|キャンペーン", re.I)

# 期限写法。kind 决定怎么补年月：md=月日、slash=斜杠、day=只有日、rel=今晚/本日。
_END_FORMS: tuple[tuple[str, re.Pattern], ...] = (
    ("md", re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日[^。]{0,16}?(?:まで|截止|结束|终止|止|为止)")),
    ("md", re.compile(r"(?:至|截止|到|截至)\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")),
    ("md", re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*为止")),
    ("slash", re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})\s*日?[^。]{0,16}?(?:まで|截止|结束|终止|止|为止)")),
    ("slash", re.compile(r"(?:至|截止|到|截至)\s*(\d{1,2})/(\d{1,2})")),
    ("day", re.compile(r"(?:至|截止|到|截至)\s*(\d{1,2})\s*日(?!\s*[本发発])")),
    ("day", re.compile(r"(?<!\d)(\d{1,2})\s*日\s*(?:截止|为止|まで)")),
    # 「到今晚二十四点」「本日 24:00」——截止日就是这条消息当天（明日则次日）。
    ("rel", re.compile(r"(今晚|本日|今日|今天|明日|明天)[^。]{0,6}?"
                       r"(?:二十四点|24\s*点|24[:：]00|24\s*时|零点|深夜)")),
)

# 结果通报：期限已过，但讲的是「结束了 / 谁中了」，不是还在卖的贩售信息。
# 日文原推常写 `抽選を行い、当選者の方にご連絡致しました`，中文概括写
# 「完成抽奖 / 已通知中奖者」——两边都要认，否则结果通报会被当成过期贩售删掉。
RESULT_WORDS = re.compile(
    r"完成抽奖|抽奖结果|抽選結果|抽选结果|中奖|中獎|得奖|中選|已通知|通知中奖"
    r"|已发货|已寄出|已发放|发放完毕|结果公布"
    r"|抽選を行|抽選を実施|抽選会|当選者|当選発表|ご連絡致しました|ご連絡済み")

# 未来发售：`12/25 发售`、`1月19日定档`。只在**别的句子**里出现时才保命。
RELEASE_WORDS = re.compile(r"发售|発売|开卖|上架|上市|上线|推出|定档|配信开始|リリース")
DATE_ANY = re.compile(r"(?:\d{1,2}\s*月\s*\d{1,2}\s*日|(?<!\d)\d{1,2}/\d{1,2})")

_SENTENCE_SPLIT = re.compile(r"[。！？!?；;\n]")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(str(text or "")) if s.strip()]


def _resolve(kind: str, month: str | None, day: str, anchor: date) -> date | None:
    d = int(day)
    if kind == "day":
        month_no = anchor.month
        year = anchor.year
        if d < anchor.day:          # 已经过去的「日」只可能是下个月
            month_no += 1
            if month_no > 12:
                month_no, year = 1, year + 1
        try:
            return date(year, month_no, d)
        except ValueError:
            return None
    m = int(month or 0)
    if not 1 <= m <= 12:
        return None
    year = anchor.year
    # 跨年：锚在 12 月说「1 月」是明年，锚在 1 月说「12 月」是去年。
    if m < anchor.month - 6:
        year += 1
    elif m > anchor.month + 6:
        year -= 1
    try:
        return date(year, m, d)
    except ValueError:
        return None


def _candidates(text: str, anchor: date) -> list[tuple[int, int, date, str, str, str]]:
    """(起, 止, 日期, 原文, 类别, 所在句)。只有日的写法若与月日写法重叠就丢。"""
    body = str(text or "")
    found: list[tuple[int, int, date, str, str, str]] = []
    for kind, pattern in _END_FORMS:
        for m in pattern.finditer(body):
            if kind == "rel":
                # 「本日24点」= 当天结束；「明日24点」= 次日结束。截止日按最后一天记。
                offset = 1 if m.group(1) in ("明日", "明天") else 0
                when = anchor + timedelta(days=offset)
            else:
                if kind == "day":
                    month = None
                    day = m.group(1)
                else:
                    month, day = m.group(1), m.group(2)
                when = _resolve(kind, month, day, anchor)
            if when is None:
                continue
            sentence = next((s for s in _sentences(body) if m.group(0) in s), body)
            found.append((m.start(), m.end(), when, m.group(0), kind, sentence))
    # `11月9日截止` 会被「月日」与「只有日」各命中一次；保留信息更全的月日写法。
    wide = [(a, b) for a, b, *rest in found if rest[2] in ("md", "slash")]
    out = []
    for a, b, when, raw, kind, sentence in found:
        if kind == "day" and any(a < wb and wa < b for wa, wb in wide):
            continue
        out.append((a, b, when, raw, kind, sentence))
    return out


def find_expired(text: str, today: date, anchor: date | None = None,
                 cfg: dict | None = None) -> dict | None:
    """这条正文里是否有「已经结束的贩售」；命中就给出删除 / 保留的理由。

    返回 `{"drop": bool, "end": "YYYY-MM-DD", "raw": 期限写法, "context": 所在句,
    "why": 说明}`；没有可判定的期限就返回 None。
    """
    cfg = cfg or {}
    if cfg.get("enabled") is False:
        return None
    body = str(text or "")
    if not body or not SALE_WORDS.search(body):
        return None
    base = anchor or today
    cands = _candidates(body, base)
    if not cands:
        return None
    past = [c for c in cands if c[2] < today]
    if not past:
        return None
    # 结果通报：期限已过，但这条讲的是「结束了 / 谁中了」。
    # 整条文本一起判，而不是只判命中的那句：日期常落在日文原推里、结论落在中文
    # 概括里（`抽選を行い…ご連絡致しました` + 「已通知中奖者」）。
    if cfg.get("keep_if_result_report", True) and RESULT_WORDS.search(body):
        return None
    latest = max(past, key=lambda c: c[2])
    _start, _end, when, raw, _kind, sentence = latest
    # 另一句带未来发售：删掉会连带丢新闻，保留并说明。
    # 「另一句」必须整句都只谈未来——中文概括与日文原推是同一件事的两个文本面，
    # 若那句自己也写了已经过去的日期（`11/27 发售作的特典…11/16 定下`），
    # 它就不是另一条新闻，只是同一句的另一种写法，不能拿来豁免。
    if cfg.get("keep_if_future_release", True):
        for other in _sentences(body):
            if other == sentence:
                continue
            dates = [d for d in (_guess(raw_date, base)
                                 for raw_date in DATE_ANY.findall(other)) if d]
            if not dates or any(d < today for d in dates):
                continue
            if RELEASE_WORDS.search(other):
                upcoming = [d for d in dates if d >= today]
                if upcoming:
                    return {"drop": False, "end": when.isoformat(), "raw": raw,
                            "context": sentence,
                            "why": f"贩售已过（{raw}），但另一句有未来发售 {upcoming[0]}，保留"}
    return {"drop": True, "end": when.isoformat(), "raw": raw,
            "context": sentence, "why": f"贩售结束于 {when}（{raw}）"}


def _guess(raw: str, anchor: date) -> date | None:
    """`12/25` / `1月19日` → 日期（按锚日补年，判未来用）。"""
    text = str(raw or "")
    m = re.match(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        return _resolve("md", m.group(1), m.group(2), anchor)
    m = re.match(r"(\d{1,2})/(\d{1,2})", text)
    if m:
        return _resolve("slash", m.group(1), m.group(2), anchor)
    return None


def expiry_note(cfg: dict) -> str:
    """给正本 / 报告用的一句话口径。"""
    return str(cfg.get("basis") or "按成形日判定：结束日早于成形日即删除")


__all__ = ["find_expired", "SALE_WORDS", "RESULT_WORDS", "expiry_note", "_guess"]
