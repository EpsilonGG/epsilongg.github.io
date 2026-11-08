# audio-translate

DLsite「みんなで翻訳」音声作品的字幕管线：**音频 → 带时间戳的 SRT（默认日文，加 `--translate` 出简体中文）**。
全本地运行，CPU 即可。默认路径不加载翻译模型。

## 安装

```bash
pip install faster-whisper pypdf      # 约 250MB（含 ctranslate2 / numpy）
```

翻译走任何 OpenAI 兼容端点，二选一：

```bash
# A. Ollama（最省事）
ollama pull qwen3:4b                  # 2.5GB，质量明显好过 1.7b

# B. llama.cpp server + 自备 GGUF
llama-server -m Qwen3-4B-Instruct-2507-Q4_K_M.gguf -c 2048 --port 8080 -t 4 -ngl 0 --no-warmup
```

ASR 模型放 `work/lv3-ct2/`（CTranslate2 格式，**fp16 3.09GB → int8 运行时约 1.9GB**）：

```
Systran/faster-whisper-large-v3          # Whisper large-v3 全量，32 层 decoder
```

> **为什么必须是全量版**：词级时间戳走 CTranslate2 的 `model.align()`（DTW），
> 它读 `config.json` 的 `alignment_heads`。蒸馏模型的 decoder 只有 2 层，
> 而配置里指到第 25 层 → **越界段错误**。全量版 32 层，索引才成立。
>
> 换模型前先确认：`alignment_heads` 的最大层号 < decoder 层数。
> GGML/CT2 头里 `n_text_layer` 就是 decoder 层数（magic `0x67676d6c` 后第 11 个 u32）。

## 用法

**默认只出一个文件：带时间戳的日文 SRT（`.ja.srt.txt`）。** 不加载翻译模型，纯 ASR + 断句。

```bash
# 只要日文 SRT（默认，不需要 MT 端点）
python pipeline.py --audio track01.mp3

# 要中文译文：加 --translate，并给 MT 端点
python pipeline.py --audio track01.mp3 --translate \
    --mt-url http://127.0.0.1:8080/v1 --mt-model Qwen3-4B-Instruct-2507-Q4_K_M.gguf \
    --glossary samples/glossary.tsv

# 音频 + 台本（台本按顺序覆盖 ASR 文本，时间轴仍来自 ASR）
python pipeline.py --audio track01.mp3 --script 台本.txt

# 模型 decoder 层数不够时，退回 segment 时间
python pipeline.py --audio track01.mp3 --asr-model work/model-ct2 --no-word-ts

# 不装模型，先看管线形状
python pipeline.py --audio demo.wav --mock
```

只有台本没有音频时直接退出——**SRT 必须有时间戳**，光有台本做不出来。

输出目录 `out/` 里**只有一个文件**：

| 文件 | 内容 |
|---|---|
| `<base>.ja.srt.txt` | 日文，SRT 格式（默认） |
| `<base>.zh.srt.txt` | 简体中文，SRT 格式（`--translate` 时） |

两级缓存，改下游参数时不用重跑上游：

| 文件 | 内容 | 重跑用 |
|---|---|---|
| `work/<名字>.asr.<模型>-<word\|seg>.json` | ASR 分段 | `--redo-asr` |
| `work/<名字>.zh.json` | 译文（带模型名做 key，仅 `--translate` 时） | `--redo-mt` |

> 缓存按**模型名 + 时间轴策略**分档。早先只按文件名索引，换了模型还读旧缓存，
> 会让人以为新模型没变好——这个坑很贵。

## 时间轴怎么来的

字幕边界取自**词级时间戳**，不取 Whisper 的 segment 边界。

segment 是 30 秒窗口的产物：边界会退到整秒，还会一条横跨十几秒塞进三句话。
日语在 faster-whisper 里走 `split_tokens_on_unicode`，**词级时间戳实际是字级的**，
正好是打轴要的粒度。

`asr.group_words()` 按「句末标点 / 停顿 > 0.45s / 超 11 秒 / 超 24 字」拼句，
时间直接取首词 `start` 和末词 `end`，**不做比例切分**。超限时回头在本段内部
最大的停顿处断开——日语没空格，就地硬切会切在词中间（`着替` / `えましょう`）。

`asr.snap_to_speech()` 再把边界吸附到真实的声音起止（±0.6 秒内），
Whisper 给的边界常落在静音里。

## 只跳纯静音，绝不切词

早先的做法是「算能量、切人声区、插静音拼接、按映射表还原」。**它在这批素材上是错的**：

| 文件 | −42dB 下判定的人声 | 后果 |
|---|---|---|
| `だめみん` | 37% | `ネットプリント` 被切成 `ネットプリン` + `トしなきゃいけないから` |
| `やみみん` | 41%（**33% 真实语音被当静音砍掉**） | 大面积漏词、碎片化 |

现在只做一件事：**跳过真正的数字静音**——整段低于 −55dB 且持续 ≥1.5 秒。
这种区间里没有任何声学信息，跳过零风险；有声音的一律整段保留。

```python
speech_spans(pcm)   # → [(start, end)]，只剔纯静音
```

实测：`だめみん` 762 秒 → 522 秒需识别（跳过 240 秒）；`やみみん` 1505 秒 → 1495 秒
（密集录音几乎不省，这是正常的）。

拼接时块间插 0.3 秒静音，让模型在缝上断句；词时间经映射表还原到原始时间轴
（落在缝里的起点吸到下一块开头、终点吸到上一块结尾）。

## 不要给 initial_prompt

同一段 0–40 秒，只改提示词：

| 配置 | 输出 | 耗时 |
|---|---|---|
| 无提示词 | `なんか今日空気清浄機が` / `めちゃくちゃ鳴って` / `いやー久しぶりです` | **97 秒** |
| `以下は日本語の会話です…` | 把这句当正文吐出来，顶掉 8–16 秒真实对话 | — |
| `句読点を付けて書き起こします。` | `私のお気に入りの動画です` **连出 8 次** | 241 秒 |

**提示词既毁内容又烧 2.5 倍时间。** large-v3 自己会加标点，不需要它。
`asr.PROMPT` 已置 `None`。

## 规则实现

| 规范条款 | 代码位置 | 行为 |
|---|---|---|
| 单条 1–12 秒 | `seg.to_cues` | 不足 1s 拉长，超 12s 交给 `split_long` |
| 超 12s 且拆不开 | `seg.split_long` | 有强标点就按句拆；拆不出可读两半就**等分重复整句** |
| 两人重叠 | `seg.resolve_overlaps` | 默认 `duplicate`：head / 双行 / tail 三段，时间相连；`--overlap merge` 走官方合并写法 |
| 重叠 < 1 秒 | 同上 | 直接在前一条结束处切开（规范允许） |
| 开始前 0.5s 内 | `to_cues(lead=0.3)` | 默认提前 0.3s，可调 |
| 省略号 | `seg.normalize` | `……` / `...` / `。。。` / `【…】` 一律归一成 `…` |
| 双人同框 | 重叠区双行 | 只有重叠那一格是两行，其余保持单行 |

## 校验

```bash
python check_subs.py out/track01.ja.srt.txt --ref work/track01.asr.lv3-ct2-word.json
```

查：时长越界、重叠 ≥1s、超过 2 行、省略号写法（中文版 `…` / 英文版 `...`）、
开始时间晚于或早于台词 0.5s 以上、字幕早于声音消失。

## 单元测试

```bash
python -m unittest discover -s tests -v     # 14 条，覆盖断句与重叠
```

## 资源预算

默认路径（只出日文 SRT，不加载翻译模型）：

| 组件 | 磁盘 | 运行时 |
|---|---|---|
| Python 依赖 | ~250 MB | ~150 MB |
| large-v3 (CT2 int8) | ~3.1 GB（fp16 存档） | ~1.9 GB（实测峰值 2135 MB） |
| **合计** | **~3.4 GB** | **峰值 ~2.2 GB** |

加 `--translate` 再叠一个 Qwen3-4B Q4_K_M（磁盘 ~2.5 GB / 运行时 ~2.6 GB）；
ASR 与 MT 串行，不同时驻留，内存峰值仍是 ~2.6 GB。

本机实测环境：Ryzen 7 3700U（4 核 15W）/ 5.88 GB RAM / 无 CUDA。

| 环节 | 实测 |
|---|---|
| ASR（large-v3 全量，词级时间戳） | RTF 2.4–3.5 |
| 12.7 分钟音频，默认出日文 SRT | 约 20–27 分钟 |
| MT Qwen3-4B（`--translate`） | 约 6 秒/条 |

> **内存是这台机器的瓶颈，不是 CPU。** 物理 5.88GB，已提交 13.19GB，页面文件用 2.92GB。
> 只剩 0.86GB 可用时 large-v3 会疯狂换页，RTF 从 2.4 涨到 3.5。
> 跑之前关掉 Chrome / 微信 / SGTool 能明显提速。

命中缓存后（只改断句/时间轴）几秒出新版。

## 已知限制

**ASR：**

- **`initial_prompt` 会触发复读循环**，已禁用。若将来要加，必须先在这批素材上验证。
- **蒸馏模型不能用词级时间戳**（decoder 层数不够，DTW 越界段错误）。要时间精度只能上全量版。
- **纯音乐/环境音段可能仍出幻觉**。`drop_silent_words()` 只删落在 −55dB 以下的词，
  BGM 段能量高，删不掉。这类段落仍需要人耳过一遍。
- **同音字错认**：`なって` → `鳴って`、`ネット` → `ネ`。整句意思不受影响，但专有名词要核。
- 1 秒以下的轨道存不了字幕，本工具不处理，需要人工写进备注栏。

**翻译（只有 `--translate` 才涉及）：**

- **至少要 4B。** Qwen3-1.7B 实测把 `久しぶりです` 译成「很久没去了」、`ちょっといて` 译成「有点冷」——
  按字面猜，不是翻。4B 明显好，但仍会把 `なんか` 一律译成「哪里」。
- 逐条翻译拿不到上下文。同一句话被 ASR 切成两半时，模型只能各译一半。

**其它：**

- 台本对齐是**按顺序配对**，不是真正的强制对齐。条数不一致时会退回 ASR 文本并提示。
- 校验器只覆盖能机检的条款；「连起来读是否自然」仍然要人听。

## 走过的弯路（别再走）

| 方案 | 为什么不行 |
|---|---|
| `large-v3-turbo` | 词级时间戳能用（4 层 decoder，头 ≤3），但日语文本明显差：`わーか今日`、`空気清入` |
| `whisper.cpp` + kotoba q5_0 | **RTF 5.4**，比 faster-whisper 慢 5 倍；时间戳落整秒 |
| 手改蒸馏模型的 `alignment_heads` 为 `[[0,0]]` | 不崩了，但 DTW 全是垃圾（词时间 0 长度），还会让 `hallucination_silence_threshold` 删掉 40 秒内容 |
| `kotoba-whisper-v2.1-ct2`（jctv-tech 转换） | 1.51GB，同样是蒸馏版，头也指到第 25 层 |
| 能量 VAD 预切 | 见上，会切词、会砍掉真实语音 |
| 逐人声区单独识别 | 时间最准，但 whisper 每次按 30 秒窗口算，8 个小区 = 240 秒编码量（RTF 5.5） |
