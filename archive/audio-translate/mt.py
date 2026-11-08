"""日译中适配层。走任何 OpenAI 兼容端点：Ollama / llama.cpp / LM Studio / vLLM。"""

import json
import re
import urllib.error
import urllib.request

SYSTEM = (
    "你是日语音声作品的字幕翻译。下面是一段对话里连续的台词，"
    "请结合上下文把每条译成简体中文。\n"
    "规则：\n"
    "1. 只输出「编号. 译文」，编号与输入一一对应，不要合并或拆分条目；\n"
    "2. 不要解释、不要加注、不要输出原文；\n"
    "3. 译文里绝对不能残留日文假名，语气词也要译成中文（「え」→「欸」）；\n"
    "4. 只有原文本身带省略号或语尾拖长时才用单个 …，否则不要加；\n"
    "5. 口语、拟声词按语境译成自然的中文，不要直译；\n"
    "6. 保持原有的语气与亲密程度，不要书面化；\n"
    "7. 不要补原文没有的内容，拿不准就照字面直译。"
)

_IDX = re.compile(r"^\s*(\d+)\s*[.．、)）]\s*(.*)$")
_KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
# 模型会把控制记号原样吐回来（实测 Qwen3-4B 输出过「先干点事吧/no_think」），必须清掉
_NOISE = re.compile(r"\s*/no_think|<\|[^|]*\|>")


def _clean(s):
    return _NOISE.sub("", s or "").strip()


class Translator:
    def __init__(self, base_url="http://127.0.0.1:11434/v1", model="qwen3:1.7b",
                 api_key="local", timeout=180, glossary=None, batch=8):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.glossary = glossary or []
        self.batch = batch
        self.untranslated = []  # [(index, 原文, 译文)]，译不出来的条目

    def _post(self, payload):
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def _ask(self, lines):
        extra = ""
        if self.glossary:
            pairs = "；".join(f"{a}→{b}" for a, b in self.glossary)
            extra = f"\n术语对照（优先采用）：{pairs}"
        user = extra + "\n\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(lines, 1))
        name = self.model.lower()
        # Instruct-2507 是**非思考**模型，加 /no_think 只会被它当正文吐回来
        if "qwen3" in name and "2507" not in name and "instruct" not in name:
            user += "\n/no_think"  # 关掉思考模式，否则会吐推理过程
        data = self._post({
            "model": self.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
        })
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _parse(raw, n):
        got = {}
        cur = None
        for line in raw.replace("\r", "").split("\n"):
            m = _IDX.match(line)
            if m:
                cur = int(m.group(1))
                got[cur] = m.group(2).strip()
            elif cur is not None and line.strip():
                got[cur] += line.strip()
        for k in list(got):
            got[k] = _clean(got[k])
        if len(got) == n and all(got.get(i) for i in range(1, n + 1)):
            return [got[i] for i in range(1, n + 1)]
        return None

    def translate(self, texts):
        self.untranslated = []
        out = []
        for i in range(0, len(texts), self.batch):
            out.extend(self._chunk(texts[i:i + self.batch]))
        return out

    def _chunk(self, chunk):
        """译一批。格式崩了或译文里还剩假名，就逐条重试。

        绝不能默默把日文原文当译文塞回去——那样 SRT 里会混进日文，
        而且下游完全看不出来。实在译不出就记下来，由调用方决定怎么办。
        """
        res = self._parse(self._ask(chunk), len(chunk))
        if res is None:
            res = [None] * len(chunk)
        for i, r in enumerate(res):
            if r and not _KANA.search(r):
                continue
            one = self._parse(self._ask([chunk[i]]), 1)
            if one and not _KANA.search(one[0]):
                res[i] = one[0]
            elif r is None:
                res[i] = one[0] if one else chunk[i]
        for i, r in enumerate(res):
            if not r or _KANA.search(r):
                self.untranslated.append((i, chunk[i], r))
                res[i] = r or chunk[i]
        return res


class MockTranslator:
    """不装模型时验证管线用。demo 句给真译文，其余加前缀，便于确认对齐。"""

    DEMO = {
        "こんにちは、いい夜ですね。": "晚上好，今晚夜色真好。",
        "ええ、本当に。少し冷えてきました。": "嗯，是啊。有点凉起来了。",
        "そんな夜は、温かいコーヒーでもどうですか。": "这样的夜晚，来杯热咖啡怎么样？",
        "ありがとう、いただきます。": "谢谢，那我就不客气了。",
        "ゆっくりでいいですよ。時間はたっぷりありますから、焦らないでくださいね。":
            "慢慢来就好。时间很充裕，不用着急。",
    }

    def __init__(self, *_, **__):
        self.untranslated = []

    def translate(self, texts):
        return [self.DEMO.get(t, f"（译）{t}") for t in texts]


def load_glossary(path):
    if not path:
        return []
    pairs = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for sep in ("\t", "=>", "=", ","):
            if sep in line:
                a, b = line.split(sep, 1)
                pairs.append((a.strip(), b.strip()))
                break
    return pairs
