"""SRT 读写。时间戳统一 00:00:00,000。"""

import re
from dataclasses import dataclass

TS = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


@dataclass
class Cue:
    start: float
    end: float
    text: str

    @property
    def dur(self):
        return self.end - self.start


def fmt_ts(t: float) -> str:
    if t < 0:
        t = 0.0
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _sec(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def parse_srt(text: str):
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        block = block.strip("\n")
        if not block.strip():
            continue
        m = TS.search(block)
        if not m:
            continue
        lines = block.split("\n")
        # 时间轴之前可能有索引行
        idx = next(i for i, l in enumerate(lines) if TS.search(l))
        body = [l.rstrip() for l in lines[idx + 1:] if l.strip()]
        cues.append(Cue(_sec(*m.group(1, 2, 3, 4)), _sec(*m.group(5, 6, 7, 8)), "\n".join(body)))
    return cues


def write_srt(cues, path: str, encoding="utf-8"):
    out = []
    for i, c in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{fmt_ts(c.start)} --> {fmt_ts(c.end)}")
        out.append(c.text)
        out.append("")
    with open(path, "w", encoding=encoding, newline="\n") as f:
        f.write("\n".join(out))
