"""音声作品字幕管线：音频/台本 → 简体中文 SRT（+ 日文 txt）。

    python pipeline.py --audio track01.mp3 --mock
    python pipeline.py --audio track01.mp3 --script 台本.txt \
        --mt-url http://127.0.0.1:11434/v1 --mt-model qwen3:1.7b
    python pipeline.py --script 台本.pdf            # 无音频，只出纯文本
"""

import argparse
import json
import os
import sys
from pathlib import Path

import seg as segmod
import srtio
from check_subs import check
from mt import MockTranslator, Translator, load_glossary


def read_script(path):
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            sys.exit("读 PDF 需要 pypdf：pip install pypdf")
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
    else:
        text = p.read_text(encoding="utf-8-sig")

    lines = []
    for line in text.replace("\r", "").split("\n"):
        t = line.strip()
        if not t:
            continue
        # 台本常见的行首标记：人名、时间码、括号注释
        if t.startswith(("【", "［", "[", "（", "(")) and len(t) < 12:
            continue
        lines.append(t)
    return lines


def align_script(segs, lines):
    """按顺序把台本行贴到 ASR 段上。条数一致才用，否则保留 ASR 文本。"""
    if len(lines) == len(segs):
        for s, t in zip(segs, lines):
            s.text = t
        return True, ""
    return False, f"台本 {len(lines)} 行 / ASR {len(segs)} 段，条数不一致，改用 ASR 文本"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio")
    ap.add_argument("--script", help="日语台本 .txt / .pdf")
    ap.add_argument("--out", default="out")
    ap.add_argument("--mock", action="store_true", help="不加载模型，验证管线")
    ap.add_argument("--asr-model", default="work/lv3-ct2")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--beam-size", type=int, default=1,
                    help="1 最快；这台机器上 5 的质量提升不值那 60%% 时间")
    ap.add_argument("--no-word-ts", action="store_true",
                    help="关掉词级时间戳，退回 segment 时间（蒸馏模型 decoder 层数不够时用）")
    ap.add_argument("--redo-asr", action="store_true", help="忽略 work/<名字>.asr.json 缓存")
    ap.add_argument("--redo-mt", action="store_true", help="忽略 work/<名字>.zh.json 缓存")
    ap.add_argument("--mt-url", default="http://127.0.0.1:11434/v1")
    ap.add_argument("--mt-model", default="qwen3:1.7b")
    ap.add_argument("--glossary")
    ap.add_argument("--overlap", default="duplicate", choices=["duplicate", "merge"])
    ap.add_argument("--translate", action="store_true",
                    help="出中文译文（默认只出日文 SRT）。要连 MT 端点")
    ap.add_argument("--lead", type=float, default=segmod.LEAD)
    ap.add_argument("--tail", type=float, default=segmod.TAIL)
    a = ap.parse_args()

    if not a.audio and not a.script:
        sys.exit("至少要给 --audio 或 --script")

    base = Path(a.audio or a.script).stem
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    # 1. 取日文段
    if a.audio:
        if a.mock:
            segs, info = __import__("asr").mock()
        else:
            # ASR 是这条管线里最贵的一步（25 分钟音频要跑半小时），
            # 结果落盘缓存；重跑翻译时不用再听一遍。
            # 缓存按「模型 + 时间轴策略」分档：换了模型还读旧缓存是最难发现的错，
            # 会让人以为新模型没变好。
            tag = f"{Path(a.asr_model).name}-{'seg' if a.no_word_ts else 'word'}"
            cache = Path("work") / f"{base}.asr.{tag}.json"
            if cache.exists() and not a.redo_asr:
                raw = json.loads(cache.read_text(encoding="utf-8"))
                segs = [segmod.Seg(r["start"], r["end"], r["text"]) for r in raw]
                info = None
                print(f"ASR: 复用缓存 {cache.name}（{len(segs)} 段）")
            else:
                segs, info = __import__("asr").transcribe(
                    a.audio, a.asr_model, a.device, a.compute_type,
                    beam_size=a.beam_size, word_ts=not a.no_word_ts)
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(
                    [{"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text}
                     for s in segs], ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"ASR: {len(segs)} 段（已缓存到 {cache.name}）"
                      + (f"，语言 {info.language}" if info else ""))
    else:
        segs = []

    # 2. 台本对齐
    script_lines = read_script(a.script) if a.script else None
    if script_lines and segs:
        ok, why = align_script(segs, script_lines)
        print("台本对齐: " + ("已替换 ASR 文本" if ok else why))

    # 3. 没有音频就出不了 SRT（SRT 必须有时间戳）
    if not segs:
        sys.exit("只有台本没有音频，做不出 SRT。要么给 --audio，要么直接用台本人工译。")

    # 4. 译文（可选）。默认只出日文 SRT，加 --translate 才翻成中文。
    lang = "ja"
    if a.translate:
        lang = "zh"
        tr = MockTranslator() if a.mock else Translator(
            a.mt_url, a.mt_model, glossary=load_glossary(a.glossary))
        # 译文也缓存：调断句/时间轴时不用再让模型重译一遍（4B 上 90 条要 7 分钟）
        zh_cache = Path("work") / f"{base}.zh.json"
        key = f"{a.mt_model}|{a.glossary or ''}"
        saved = None
        if zh_cache.exists() and not a.redo_mt:
            cand = json.loads(zh_cache.read_text(encoding="utf-8"))
            if cand.get("key") == key and len(cand.get("texts", [])) == len(segs):
                zh, saved = cand["texts"], cand
                print(f"译文: 复用缓存 {zh_cache}（{len(zh)} 条）")
        if saved is None:
            zh = tr.translate([s.text for s in segs])
            zh_cache.parent.mkdir(parents=True, exist_ok=True)
            zh_cache.write_text(json.dumps({"key": key, "texts": zh},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
        if len(zh) != len(segs):
            sys.exit(f"译文条数 {len(zh)} 与语音段 {len(segs)} 不一致，停下来查")
        if getattr(tr, "untranslated", None):
            print(f"警告: {len(tr.untranslated)} 条没译出来，SRT 里会留着日文原文")
            for i, src, got in tr.untranslated[:10]:
                print(f"  #{i + 1} {src} → {got}")
        for s, t in zip(segs, zh):
            s.text = t

    # 5. 断句 + 时间轴
    cues = segmod.build(segs, a.overlap, a.lead, a.tail)

    # 6. 只出一个文件：srt 格式的 txt
    srt_path = out / f"{base}.{lang}.srt.txt"
    srtio.write_srt(cues, str(srt_path))
    print(f"字幕: {len(cues)} 条 → {srt_path}")

    # 7. 自检（参考分段在内存里算，不落盘，免得又多一堆文件）
    ref = [{"start": s.start, "end": s.end} for s in segs]
    errs, warns = check(cues, ref, lang)
    print(f"自检: {len(errs)} 错误 / {len(warns)} 提醒")
    for i, c, m in errs[:10]:
        print(f"  [ERROR] #{i} {c}: {m}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
