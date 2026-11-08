"""日语 ASR 适配层。faster-whisper + large-v3（CPU int8）。

## 为什么不再用能量 VAD 预切

早先的做法是「算能量、切人声区、插静音拼接、按映射表还原」。它在这批素材上
是错的：`だめみん` 在 -42dB 阈值下只认 37% 的人声，`やみみん` 更糟——把 33%
的真实语音当静音砍掉。被砍的地方就出现 `ネットプリン` + `トしなきゃいけないから`
这种切口，译文跟着错成「宠物打印」。

现在只做一件事：**跳过真正的数字静音**（-55dB 以下、持续 ≥1.5 秒）。
这种区间里没有任何声学信息，跳过零风险；有声音的一律整段保留。

## 时间轴从哪来

字幕边界取自**词级时间戳**（Whisper DTW 对齐），不取 segment 边界。
segment 是 30 秒窗口的产物，会退到整秒、还会一条横跨十几秒塞三句话。
日语在 faster-whisper 里走 `split_tokens_on_unicode`，词级时间戳实际上是
**字级**，正好是打轴要的粒度。

词级时间戳要求模型的 `alignment_heads` 落在真实 decoder 层范围内。
蒸馏模型的 decoder 只有 2 层，配置里却指到第 25 层，`model.align()` 会直接
段错误——这就是之前 `word_timestamps=True` 崩掉的原因。
"""

import sys
from collections import namedtuple

import numpy as np

from seg import Seg

# 一个词：起止时间、文本、模型给的概率
Word = namedtuple("Word", "start end text prob")

# 数字静音大约 -63dB。低于这个值说明整段没有声音，模型在那儿只会编词。
SILENT_DB = -55.0

# 只跳过持续这么久以上的纯静音，短的气口一律保留（气口里常常有语气词）
SILENCE_MIN_LEN = 1.5

# 拼接块之间插的静音，让模型在缝上断句
CONCAT_GAP = 0.30

# 词间超过这个间隔算换气，可以断句
PAUSE = 0.45

# 句末标点，遇到就收一条
SENT_END = "。！？!?…"


def decode(path, rate=16000):
    """自己解码成 16k 单声道 float32，绕开 faster-whisper 与 PyAV 的版本不兼容。"""
    import av

    with av.open(path) as c:
        res = av.AudioResampler(format="s16", layout="mono", rate=rate)
        chunks = []
        for frame in c.decode(audio=0):
            for f in res.resample(frame):
                chunks.append(f.to_ndarray().reshape(-1))
        for f in res.resample(None):
            chunks.append(f.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


# 不要给 initial_prompt。实测它会在这类素材上触发复读循环：
# 给「以下は日本語の会話です…」→ 模型把这句当正文吐出来，顶掉 8-16 秒的真实对话；
# 给一句短的 → 变成「私のお気に入りの動画です」连出 8 次，耗时从 97 秒涨到 241 秒。
# large-v3 本身就会加标点，不需要提示词。
PROMPT = None


def frame_db(pcm, rate=16000, frame=0.02):
    """每 20ms 一帧的 dBFS 包络。"""
    hop = int(rate * frame)
    n = len(pcm) // hop
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    frames = pcm[:n * hop].reshape(n, hop).astype(np.float64)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return (20 * np.log10(np.maximum(rms, 1e-8))).astype(np.float32)


def speech_spans(pcm, rate=16000, floor_db=SILENT_DB,
                 min_len=SILENCE_MIN_LEN, pad=0.25, smooth=0.40):
    """返回要送去识别的区间 [(start_s, end_s)]。

    只剔除「持续 ≥min_len 秒、整段都低于 floor_db」的纯静音。
    其余全部保留——宁可多算，不能漏词。

    `smooth` 是关键：先对包络做 0.4 秒滑动平均再判静音。不平滑的话，
    静音里一个 1-2 帧的爆音（实测有 −27dB 的）就能把整段静音切成两半，
    每半都不足 min_len，于是一整段噪声被当成语音送进模型，模型在上面
    编出「ほー」「ーー…」这种字幕。
    """
    dur = len(pcm) / rate
    if dur <= 0:
        return []
    db = frame_db(pcm, rate)
    if len(db) == 0:
        return [(0.0, dur)]

    frame = 0.02
    k = max(1, int(smooth / frame))
    if len(db) > k:
        db = np.convolve(db, np.ones(k, dtype=np.float32) / k, mode="same")

    quiet = db <= floor_db
    if not quiet.any():
        return [(0.0, dur)]

    # 找连续静音段
    edges = np.flatnonzero(np.diff(np.concatenate(([0], quiet.view(np.int8), [0]))))
    runs = [(a * frame, b * frame) for a, b in zip(edges[::2], edges[1::2])
            if (b - a) * frame >= min_len]
    if not runs:
        return [(0.0, dur)]

    # 静音段的反面就是要识别的段
    spans, cursor = [], 0.0
    for s, e in runs:
        if s - cursor > 0.05:
            spans.append((max(0.0, cursor - pad), min(dur, s + pad)))
        cursor = e
    if dur - cursor > 0.05:
        spans.append((max(0.0, cursor - pad), dur))
    return spans or [(0.0, dur)]


def _concat_spans(pcm, spans, rate=16000, gap=CONCAT_GAP):
    """把要识别的区间拼成一条，返回 (音轨, 映射表)。

    映射表元素 (concat_start, orig_start, length)。词时间减去 concat_start
    再加 orig_start 就是原始时间轴——因为块间插了静音，没有词会跨块。
    """
    if not spans:
        return pcm, [(0.0, 0.0, len(pcm) / rate)]
    sil = np.zeros(int(rate * gap), dtype=np.float32)
    pieces, table, cursor = [], [], 0.0
    for s, e in spans:
        chunk = pcm[int(s * rate):int(e * rate)]
        if len(chunk) == 0:
            continue
        pieces.append(chunk)
        table.append((cursor, s, len(chunk) / rate))
        pieces.append(sil)
        cursor += len(chunk) / rate + gap
    if not pieces:
        return pcm, [(0.0, 0.0, len(pcm) / rate)]
    return np.concatenate(pieces), table


def _to_orig(t, table, is_end=False):
    """拼接音轨上的时间 → 原始时间轴。

    块之间插了 0.3 秒静音，词的时间可能落在缝里。落在缝里时：
    起点吸到下一块开头，终点吸到上一块结尾——两边都往「有声」的方向靠，
    不会把字幕拉进静音。
    """
    prev_end = 0.0
    for c_start, o_start, length in table:
        c_end = c_start + length
        if t <= c_end:
            if t < c_start:
                return prev_end if is_end else o_start
            return o_start + (t - c_start)
        prev_end = o_start + length
    c_start, o_start, length = table[-1]
    return o_start + length


def _span_db(db, start, end, frame=0.02):
    """一段时间的峰值 dB。

    用峰值不用均值：轻声、气声的均值很低，但总有一个响的瞬间。
    只有真正的数字静音才是整段都低。
    """
    if len(db) == 0:
        return 0.0
    a = int(start / frame)
    b = max(int(end / frame), a + 1)
    a = max(0, min(a, len(db) - 1))
    b = max(a + 1, min(b, len(db)))
    return float(db[a:b].max())


def drop_silent_words(words, db, floor=SILENT_DB, frame=0.02, min_run=0.80):
    """丢掉落在数字静音里的词——那是模型在无声处编出来的。

    **只丢「连续一小段」**，不丢单个词。句首的清音（す / か / 自 / 立）
    本身能量就低，逐个判会被误删，实测切出 `タジオ`（スタジオ）、
    `ラオケ`（カラオケ）、`分自身`（自分自身）、`ち上がる`（立ち上がる）。
    一整段都静才是编的，一两个字的低能量不是。
    """
    quiet = [_span_db(db, w.start, w.end, frame) < floor for w in words]
    keep, gone, i = [], [], 0
    while i < len(words):
        if not quiet[i]:
            keep.append(words[i])
            i += 1
            continue
        j = i
        while j < len(words) and quiet[j]:
            j += 1
        run = words[i:j]
        if run[-1].end - run[0].start >= min_run:
            gone.extend(run)
        else:
            keep.extend(run)
        i = j
    return keep, gone


def group_words(words, max_dur=11.0, max_chars=24, pause=PAUSE):
    """把词级时间戳拼成字幕段。

    断句条件（任一）：
    - 当前词以句末标点结尾；
    - 下一个词之前的静音超过 pause；
    - 再拼下去会超过 max_dur 或 max_chars。

    超过 max_dur / max_chars 时，**回头在本段内部最大的停顿处断开**，
    而不是就地硬切——日语没有空格，硬切会切在词中间（`着替` / `えましょう`）。
    内部没有像样的停顿时才真的硬切。

    时间直接取首词 start 和末词 end，不做任何比例切分。
    """
    if not words:
        return []

    cues, cur = [], []

    def emit(ws):
        text = "".join(w.text for w in ws).strip()
        if text:
            cues.append(Seg(float(ws[0].start), float(ws[-1].end), text))

    def span_of(ws):
        return ws[-1].end - ws[0].start

    def chars_of(ws):
        return sum(len(w.text) for w in ws)

    for w in words:
        cur.append(w)
        if len(cur) > 1 and w.start - cur[-2].end > pause:
            emit(cur[:-1])
            cur = [w]
        elif w.text and w.text[-1] in SENT_END:
            emit(cur)
            cur = []
        elif span_of(cur) > max_dur or chars_of(cur) > max_chars:
            if len(cur) > 1:
                gaps = [cur[i + 1].start - cur[i].end for i in range(len(cur) - 1)]
                k = max(range(len(gaps)), key=lambda i: gaps[i])
                if gaps[k] >= 0.25:      # 真停顿才断；0.15 会把词切开
                    emit(cur[:k + 1])
                    cur = cur[k + 1:]
                    continue
            # 没有像样的停顿：再攒一点，等下一个真停顿，别硬切
            if span_of(cur) <= max_dur and chars_of(cur) <= max_chars * 1.3:
                continue
            emit(cur)
            cur = []
    emit(cur)
    return cues


def _merge_short(cues, min_dur=1.0, max_dur=11.0):
    """短于 min_dur 的段并进邻居，优先并后一条（保住「先说后停」的语感）。"""
    if not cues:
        return []
    out = list(cues)
    i = 0
    while i < len(out):
        c = out[i]
        if c.end - c.start >= min_dur:
            i += 1
            continue
        nxt = out[i + 1] if i + 1 < len(out) else None
        prv = out[i - 1] if i > 0 else None
        if (nxt is not None and "\n" not in nxt.text
                and nxt.end - c.start <= max_dur
                and nxt.start - c.end <= 1.5):
            nxt.start = c.start
            nxt.text = f"{c.text}\n{nxt.text}" if c.text else nxt.text
            out.pop(i)
            continue
        if (prv is not None and "\n" not in prv.text
                and max(prv.end, c.end) - prv.start <= max_dur):
            prv.end = max(prv.end, c.end)
            prv.text = f"{prv.text}\n{c.text}" if c.text else prv.text
            out.pop(i)
            continue
        i += 1
    return out


def _dedup_repeats(cues, window=3):
    """连续 3 条完全一样 = 复读，只留第一条。"""
    out = []
    for c in cues:
        if len(out) >= window - 1 and all(x.text == c.text for x in out[-(window - 1):]):
            continue
        out.append(c)
    return out


def snap_to_speech(cues, db, frame=0.02, window=0.60, floor=SILENT_DB):
    """把字幕边界吸附到真实的声音起止。

    Whisper 给的边界常常落在静音里（提前 0.5 秒开始、或者声音停了字幕还挂着）。
    这里在 ±window 范围内找最近的「静音→有声」跳变（起点）和
    「有声→静音」跳变（终点），把边界贴上去。

    只做保守修正：移动不超过 window，且不能让时长掉到 1 秒以下。
    """
    if len(db) == 0 or not cues:
        return cues
    dur = len(db) * frame
    voiced = db > floor

    def onset_near(t):
        """t 附近最近的一次「静音→有声」。"""
        lo = max(0, int((t - window) / frame))
        hi = min(len(voiced) - 1, int((t + window) / frame))
        if hi <= lo:
            return None
        seg = voiced[lo:hi + 1]
        edges = np.flatnonzero(np.diff(seg.astype(np.int8)) == 1)
        if len(edges) == 0:
            return None
        best = min(edges, key=lambda i: abs((lo + i + 1) * frame - t))
        return (lo + best + 1) * frame

    def offset_near(t):
        """t 附近最近的一次「有声→静音」。"""
        lo = max(0, int((t - window) / frame))
        hi = min(len(voiced) - 1, int((t + window) / frame))
        if hi <= lo:
            return None
        seg = voiced[lo:hi + 1]
        edges = np.flatnonzero(np.diff(seg.astype(np.int8)) == -1)
        if len(edges) == 0:
            return None
        best = min(edges, key=lambda i: abs((lo + i + 1) * frame - t))
        return (lo + best + 1) * frame

    out = []
    for c in cues:
        s, e = c.start, c.end
        # 起点落在静音里 → 往后贴到人声开口
        i = min(len(voiced) - 1, max(0, int(s / frame)))
        if not voiced[i]:
            o = onset_near(s)
            if o is not None and o > s and o - s <= window and e - o >= 1.0:
                s = o
        # 终点落在静音里 → 往前贴到人声收尾
        j = min(len(voiced) - 1, max(0, int((e - frame) / frame)))
        if not voiced[j]:
            o = offset_near(e)
            if o is not None and o < e and e - o <= window and o - s >= 1.0:
                e = o
        out.append(Seg(max(0.0, min(s, dur)), min(dur, e), c.text))
    return out


def drop_silent_segments(segs, db, frame=0.02, floor=SILENT_DB, ratio=0.6):
    """丢掉大部分落在静音里的段——segment 模式没有词级信息，只能按整段判。"""
    out = []
    for c in segs:
        a, b = int(c.start / frame), int((c.end) / frame)
        a, b = max(0, a), min(len(db), max(a + 1, b))
        if b <= a:
            out.append(c)
            continue
        quiet = float((db[a:b] <= floor).mean())
        if quiet >= ratio:
            continue
        out.append(c)
    return out


def transcribe(audio, model="work/lv3-ct2",
               device="cpu", compute_type="int8", language="ja",
               beam_size=1, threads=4, word_ts=True):
    """返回 (list[Seg], info)。

    word_ts=True 用词级时间戳拼句（时间准，要求模型 decoder 层数够）；
    False 退回 segment 时间（蒸馏模型只能用这个）。
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("缺 faster-whisper：pip install faster-whisper")

    pcm = decode(audio)
    rate = 16000
    dur = len(pcm) / rate
    m = WhisperModel(model, device=device, compute_type=compute_type, cpu_threads=threads)
    info = _Info(language, dur)

    spans = speech_spans(pcm, rate)
    speech = sum(e - s for s, e in spans)
    if speech < dur - 1.0:
        print(f"  跳过纯静音 {dur - speech:.0f}s（{speech:.0f}s / {dur:.0f}s 需识别）", flush=True)

    audio_in, table = _concat_spans(pcm, spans, rate)

    opts = dict(
        language=language,
        beam_size=beam_size,
        vad_filter=False,                   # 自带 Silero 在这台机器上把 60 秒判成 1.1 秒
        condition_on_previous_text=False,   # 关掉可减少复读
        no_speech_threshold=0.6,
        temperature=[0.0, 0.2],
    )
    if PROMPT:
        opts["initial_prompt"] = PROMPT
    if word_ts:
        opts["word_timestamps"] = True

    segments, _ = m.transcribe(audio_in, **opts)
    segments = list(segments)

    db = frame_db(pcm, rate)
    info.duration_after_vad = speech

    if word_ts:
        words = []
        for s in segments:
            for w in (s.words or []):
                t = w.word or ""
                if not t.strip():
                    continue
                words.append(Word(_to_orig(float(w.start), table),
                                  _to_orig(float(w.end), table, is_end=True),
                                  t, float(w.probability)))
        if not words:
            return [], info
        words, dropped = drop_silent_words(words, db)
        if dropped:
            print(f"  静音过滤: 丢掉 {len(dropped)} 个词（无声处编的）", flush=True)
        cues = group_words(words)
        cues = _merge_short(cues)
        cues = _dedup_repeats(cues)
        cues = snap_to_speech(cues, db)
        return cues, info

    out = []
    for s in segments:
        t = (s.text or "").strip()
        if t:
            out.append(Seg(_to_orig(float(s.start), table),
                           _to_orig(float(s.end), table, is_end=True), t))
    out = _dedup_repeats(out)
    out = drop_silent_segments(out, db)
    return snap_to_speech(out, db), info


class _Info:
    """TranscriptionInfo 的轻量替身：管线只用到 language 和时长。"""

    def __init__(self, language, duration):
        self.language = language
        self.duration = duration
        self.duration_after_vad = duration


def mock(_audio=None):
    """不装模型时用来验证整条管线。"""
    demo = [
        (0.8, 4.2, "こんにちは、いい夜ですね。"),
        (4.6, 9.0, "ええ、本当に。少し冷えてきました。"),
        (9.2, 15.5, "そんな夜は、温かいコーヒーでもどうですか。"),
        (14.8, 20.0, "ありがとう、いただきます。"),  # 故意和上一条重叠
        (20.5, 34.0, "ゆっくりでいいですよ。時間はたっぷりありますから、焦らないでくださいね。"),
    ]
    return [Seg(a, b, t) for a, b, t in demo], None
