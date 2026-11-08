"""字幕校验器：把 DLsite 音声字幕规范里能机检的条款跑一遍。

用法:
    python check_subs.py out/xxx.zh.srt
    python check_subs.py out/xxx.zh.srt --ref out/xxx.ja.segments.json
    python check_subs.py subs.srt --lang en

退出码 0 = 无错误，1 = 有错误，2 = 读不了。
"""

import argparse
import json
import re
import sys

from srtio import fmt_ts, parse_srt

MAX_DUR, MIN_DUR, LEAD, OVERLAP = 12.0, 1.0, 0.5, 1.0

EN_BAD = {
    "\u2026": "英语版会乱码，改用三个半角句点 ...",
    "\u2019": "弯引号，改用直引号 '",
    "\u2661": "特殊記号 ♡",
    "\u2606": "特殊記号 ☆",
    "\u266a": "特殊記号 ♪",
}
ZH_BAD = {
    "...": "省略号统一用 …（单个）",
    "。。。": "省略号统一用 …",
    "【…】": "省略号不要带框体",
}


def check(cues, ref=None, lang="zh"):
    errs, warns = [], []

    def err(c, code, msg):
        errs.append((c, code, msg))

    def warn(c, code, msg):
        warns.append((c, code, msg))

    bad = EN_BAD if lang == "en" else ZH_BAD

    for i, c in enumerate(cues, 1):
        if not c.text.strip():
            err(i, "E-EMPTY", "空字幕")
            continue
        if c.dur < MIN_DUR - 1e-6:
            err(i, "E-DUR-MIN", f"{c.dur:.2f}s < 1.0s，系统存不下")
        if c.dur > MAX_DUR + 1e-6:
            err(i, "E-DUR-MAX", f"{c.dur:.2f}s > 12.0s，必须拆")
        if len(c.text.split("\n")) > 2:
            err(i, "E-LINES", "超过 2 行，只有双人同时说话才能换行")
        for k, why in bad.items():
            if k in c.text:
                err(i, "E-CHAR", f"含 {k!r}：{why}")
        if c.text != c.text.strip():
            warn(i, "W-SPACE", "首尾有空白")

    for i, (a, b) in enumerate(zip(cues, cues[1:]), 2):
        ov = a.end - b.start
        if ov >= OVERLAP - 1e-6:
            err(i, "E-OVERLAP", f"与前一条重叠 {ov:.2f}s ≥ 1.0s，必须合并或改成双行")
        elif ov > 1e-6:
            warn(i, "W-OVERLAP", f"与前一条重叠 {ov:.2f}s（<1.0s 可接受，确认读得顺）")

    if ref:
        for i, c in enumerate(cues, 1):
            # 取与这条字幕重叠最多的语音段做锚点；没有重叠就找最近的起点
            cands = [(min(c.end, r["end"]) - max(c.start, r["start"]), r) for r in ref]
            cands = [x for x in cands if x[0] > 1e-6]
            if cands:
                a = max(cands, key=lambda x: x[0])[1]
                # 合并出来的双行条目会跨好几段。起点要对齐**最早**那段、
                # 终点对齐**最晚**那段；只锚在中间那段上会误报「比台词早」。
                first = min((x[1] for x in cands), key=lambda r: r["start"])
                last = max((x[1] for x in cands), key=lambda r: r["end"])
            else:
                near = [r for r in ref if abs(r["start"] - c.start) <= 2.0]
                if not near:
                    warn(i, "W-NOREF", "2 秒内没有对应语音段，确认不是凭空加的字幕")
                    continue
                a = min(near, key=lambda r: abs(r["start"] - c.start))
                first = last = a

            # 起点落在语音段内部 = 长句拆出来的续行，不查前导
            if c.start < first["start"] - LEAD:
                err(i, "E-LEAD", f"比台词早了 {first['start'] - c.start:.2f}s，上限 0.5s")
            elif c.start > last["end"] + 0.01:
                err(i, "E-LEAD", f"开始 {fmt_ts(c.start)} 晚于台词结束 {fmt_ts(last['end'])}")

            if c.end < last["end"] - 0.01:
                rest = last["end"] - c.end
                nxt = cues[i] if i < len(cues) else None
                covered = nxt is not None and nxt.start <= c.end + 0.05 and nxt.end >= last["end"] - 0.05
                if covered:
                    continue  # 剩下的语音被下一条接住了（长句拆分或重叠分段）
                if rest <= OVERLAP + 1e-6:
                    warn(i, "W-TAIL", f"提前 {rest:.2f}s 收尾（<1.0s，规范允许），确认可接受")
                else:
                    err(i, "E-TAIL", f"结束早于台词 {fmt_ts(last['end'])}，声音还在字幕就没了")

    return errs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srt")
    ap.add_argument("--ref", help="ASR 分段 JSON")
    ap.add_argument("--lang", default="zh", choices=["zh", "en"])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    try:
        cues = parse_srt(open(a.srt, encoding="utf-8-sig").read())
    except OSError as e:
        print(f"读不了: {e}", file=sys.stderr)
        return 2
    if not cues:
        print("没解析出字幕，检查是不是 SRT", file=sys.stderr)
        return 2

    ref = None
    if a.ref:
        ref = json.load(open(a.ref, encoding="utf-8"))
        ref.sort(key=lambda r: r["start"])

    errs, warns = check(cues, ref, a.lang)

    if a.json:
        print(json.dumps({
            "cues": len(cues),
            "errors": [{"cue": i, "code": c, "msg": m} for i, c, m in errs],
            "warnings": [{"cue": i, "code": c, "msg": m} for i, c, m in warns],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"{a.srt}: {len(cues)} 条")
        for i, c, m in errs:
            print(f"  [ERROR] #{i} {c}: {m}")
        for i, c, m in warns:
            print(f"  [WARN ] #{i} {c}: {m}")
        print(f"\n{len(errs)} 错误 / {len(warns)} 提醒")

    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
