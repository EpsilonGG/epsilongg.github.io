"""断句与时间轴规则。

三条硬约束（来自 DLsite 音声字幕规范 + 本项目约定）：
  1. 单条字幕 1–12 秒；
  2. 开始时间落在台词起始前 0.5 秒内，结束不得早于台词结束；
  3. 超过 12 秒且拆不开、或两人语音重叠时，拆成时间相连、文字相同/相对应的多条。
"""

import math
import re
from dataclasses import dataclass

from srtio import Cue

MAX_DUR = 12.0
MIN_DUR = 1.0
LEAD = 0.3
TAIL = 0.5
OVERLAP = 1.0

STRONG = "。！？；!?;"
WEAK = "，、,"
_ELLIPSIS = re.compile(r"(?:…+|\.{3,}|。{2,}|·{3,})")


@dataclass
class Seg:
    start: float
    end: float
    text: str
    speaker: str | None = None

    @property
    def dur(self):
        return self.end - self.start


def normalize(text: str) -> str:
    """省略号统一成单个 …，去掉首尾空白与多余空格。"""
    t = _ELLIPSIS.sub("…", text)
    t = t.replace("【…】", "…").replace("[…]", "…")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def _best_break(text: str):
    """在标点处找最佳断点，返回字符下标或 None。"""
    n = len(text)
    if n < 6:
        return None
    best = None
    for i, ch in enumerate(text):
        if ch not in STRONG and ch not in WEAK:
            continue
        left, right = text[: i + 1].strip(), text[i + 1:].strip()
        if len(left) < 3 or len(right) < 3:
            continue
        strong = ch in STRONG
        # 弱标点要求两边都够长，否则读起来是断的
        if not strong and (len(left) < 6 or len(right) < 6):
            continue
        score = (0 if strong else 1, abs(len(left) - len(right)))
        if best is None or score < best[0]:
            best = (score, i)
    return best[1] if best else None


def split_long(seg: Seg, max_dur=MAX_DUR, min_dur=MIN_DUR):
    """把超过 max_dur 的段拆开；拆不动就重复整句（本项目约定）。"""
    if seg.dur <= max_dur + 1e-6:
        return [seg]

    i = _best_break(seg.text)
    if i is not None:
        head, tail = seg.text[: i + 1].strip(), seg.text[i + 1:].strip()
        # 按字数比例给时间，有词级时间戳时由上层传入更准的切点
        cut = seg.start + seg.dur * (i + 1) / len(seg.text)
        if cut - seg.start >= min_dur and seg.end - cut >= min_dur:
            return (
                split_long(Seg(seg.start, cut, head, seg.speaker), max_dur, min_dur)
                + split_long(Seg(cut, seg.end, tail, seg.speaker), max_dur, min_dur)
            )

    # 拆不出可读的两半：等分时间，每段都带整句
    n = max(2, math.ceil(seg.dur / max_dur))
    step = seg.dur / n
    return [
        Seg(seg.start + k * step, seg.start + (k + 1) * step, seg.text, seg.speaker)
        for k in range(n)
    ]


def resolve_overlaps(segs, mode="duplicate", min_dur=MIN_DUR, threshold=OVERLAP):
    """处理相邻重叠。

    duplicate（默认，本项目约定）：切成时间相连的多条，重叠区间放双行。
    merge（DLsite 官方写法）：合成一条双行。
    重叠不足 1 秒：直接在前一条结束处切开，不做双行。
    """
    out = []
    for s in segs:
        if not out or s.start >= out[-1].end - 1e-6:
            out.append(s)
            continue

        prev = out[-1]
        a0, a1 = prev.start, prev.end
        b0, b1 = s.start, s.end

        if mode == "merge" or b0 <= a0 + 1e-6:
            out[-1] = Seg(a0, max(a1, b1), f"{prev.text}\n{s.text}", prev.speaker or s.speaker)
            continue

        if a1 - b0 < threshold:
            out[-1] = Seg(a0, b0, prev.text, prev.speaker)
            out.append(s)
            continue

        # 重叠 ≥1 秒：head / 重叠区双行 / tail 三段，时间相连
        if b1 >= a1:
            tail_len, tail_text, tail_spk = b1 - a1, s.text, s.speaker
            mid_end = a1
        else:
            tail_len, tail_text, tail_spk = a1 - b1, prev.text, prev.speaker
            mid_end = b1

        emit_head = (b0 - a0) >= min_dur
        emit_tail = tail_len >= min_dur

        mid_start = b0 if emit_head else a0
        mid_finish = mid_end if emit_tail else max(a1, b1)

        out.pop()
        if emit_head:
            out.append(Seg(a0, b0, prev.text, prev.speaker))
        out.append(Seg(mid_start, mid_finish,
                       f"{prev.text}\n{s.text}", prev.speaker or s.speaker))
        if emit_tail:
            out.append(Seg(mid_finish, mid_finish + tail_len, tail_text, tail_spk))

    return out


def to_cues(segs, lead=LEAD, tail=TAIL, min_dur=MIN_DUR, max_dur=MAX_DUR):
    """时间轴落位：前置 0.3s、尾部留 0.5s、夹在相邻两条之间。"""
    cues = []
    for i, s in enumerate(segs):
        start = max(0.0, s.start - lead)
        if cues:
            start = max(start, cues[-1].end)
        end = max(s.end + tail, start + min_dur)

        nxt = segs[i + 1].start if i + 1 < len(segs) else None
        if nxt is not None and end > nxt:
            end = nxt
        # 这里**不**为了凑满 1 秒把 start 往回拉：往前拉会叠加到 lead 上，
        # 触发「比台词早 0.5 秒以上」。短条目统一交给 _fix_short 处理，
        # 它借时间有上限，借不够就并进前一条。

        # 兜底：仍然超长就等分重复
        if end - start > max_dur + 1e-6:
            n = math.ceil((end - start) / max_dur)
            step = (end - start) / n
            for k in range(n):
                cues.append(Cue(start + k * step, start + (k + 1) * step, s.text))
            continue

        cues.append(Cue(start, end, s.text))
    return cues


def _fix_short(cues, min_dur=MIN_DUR, max_dur=MAX_DUR):
    """把短于 min_dur 的条目补到 1 秒。

    to_cues 会把 start 顶到前一条的 end，挤在一起时就会出现 0.2 秒的条目
    （规范不允许）。顺序是：先从前一条借时间（最多 0.2 秒，否则叠加 lead
    会触发「比台词早 0.5 秒」）；借不够就并进**下一条**（挨得近，不会拉长）；
    最后才考虑并进前一条，且合并后不得超过 max_dur——早先没这个限制，
    一个 0.6 秒的「哎」把前一条从 4 秒拉成了 73 秒。
    """
    out = []
    i, n = 0, len(cues)
    while i < n:
        c = cues[i]
        if out and c.end - c.start < min_dur:
            prev = out[-1]
            need = min_dur - (c.end - c.start)
            give = max(0.0, min(need, (prev.end - prev.start) - min_dur, 0.2))
            if give > 0:
                prev.end -= give
                c.start -= give
            if c.end - c.start < min_dur and "\n" not in c.text:
                nxt = cues[i + 1] if i + 1 < n else None
                if (nxt is not None and "\n" not in nxt.text
                        and nxt.end - c.start <= max_dur):
                    nxt.start = c.start
                    nxt.text = f"{c.text}\n{nxt.text}"
                    i += 1
                    continue
                if ("\n" not in prev.text
                        and max(prev.end, c.end) - prev.start <= max_dur):
                    prev.end = max(prev.end, c.end)
                    prev.text = f"{prev.text}\n{c.text}"
                    i += 1
                    continue
        out.append(c)
        i += 1
    return out


def build(segs, overlap="duplicate", lead=LEAD, tail=TAIL,
          min_dur=MIN_DUR, max_dur=MAX_DUR):
    clean = []
    for s in segs:
        s.text = normalize(s.text)
        if not s.text:
            continue
        clean.extend(split_long(s, max_dur, min_dur))
    clean.sort(key=lambda x: (x.start, x.end))
    clean = resolve_overlaps(clean, overlap, min_dur)
    return _fix_short(to_cues(clean, lead, tail, min_dur, max_dur), min_dur, max_dur)
