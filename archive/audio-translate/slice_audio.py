"""音频切片工具：任意格式 → 16k 单声道 WAV。不依赖 ffmpeg（走 PyAV）。"""

import argparse
import wave

import av


def slice_audio(src, dst, start=0.0, dur=None, rate=16000):
    with av.open(src) as c:
        stream = c.streams.audio[0]
        c.seek(int(start * av.time_base), stream=stream)
        res = av.AudioResampler(format="s16", layout="mono", rate=rate)
        chunks, written = [], 0
        limit = None if dur is None else int(dur * rate) * 2  # s16 = 2 字节/样本
        for frame in c.decode(stream):
            for f in res.resample(frame):
                raw = bytes(f.planes[0])
                if limit is not None:
                    raw = raw[: max(0, limit - written)]
                if raw:
                    chunks.append(raw)
                    written += len(raw)
            if limit is not None and written >= limit:
                break
        if limit is None or written < limit:
            for f in res.resample(None):
                chunks.append(bytes(f.planes[0]))
    with wave.open(dst, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(chunks))
    return written / 2 / rate


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--dur", type=float)
    a = ap.parse_args()
    print(f"{slice_audio(a.src, a.dst, a.start, a.dur):.1f}s → {a.dst}")
