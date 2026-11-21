"""原推事实层：从 `source_refs[].text` 确定性地取事实，零 LLM / 零联网。

背景（2026-11-21 用户裁决）：周报此前把日报的中文 `people[].summary` 当成
事实源——归栏、作品名、新作信号全在中文句子上判定。日报概括一旦把作品名
截断（『ライムライト・レモネードジャム』被写成「新作」）或拆错
（『放課後シンデレラ 長南陽佳は幼馴染。』被写成「长南阳佳电子书」），
周报就跟着错。原推全文其实早就在 `out/clauses/` 的 `source_refs[].text`
里（M1 L0-a），不需要重新抓、也不需要再叫一次模型。

本模块只做三件事：
1. `primary_text()`：把一条 source_ref 的**本推正文**取出来，去掉转推前缀、
   被引用的推文（引用块、`— https://…` 分隔线）与裸 URL。引用内容不是这条
   账号发布的事实，混进来会把信号与作品名错挂到别人身上。
2. `title_values()`：从本推正文的 `『』` / `《》` 取作品名，做最小去噪。
   不猜、不翻译、不相似度匹配。
3. `source_facts()`：把若干 source key 的本推正文与作品名合成一条事实文本，
   供筛选 / 归栏 / 新作分流与中文概括并排使用。

中文句子仍然是**表述层**（站点是中文站，日报概括已经付过一次 token），
但每条句子附带 `source_text` 之后，所有「是不是作品 / 是哪个作品 / 有没有
发售信号」的判定都优先看原推；中文只在原推没写时才兜底。
"""
from __future__ import annotations

import re

from .corpus import norm_title

TITLE_RE = re.compile(r"[『《]([^』》]{1,60})[』》]")
# 引用推文的分隔行：`— https://nitter.cf/...` / `—— https://...`
_QUOTE_SEP = re.compile(r"(?m)^\s*[—–]{1,3}\s*https?://")
# 引用推文的作者行：`DLsite (@DLsite_English)` / `【公式】ヴィレッジ (@vv__official)`
_QUOTE_AUTHOR = re.compile(r"(?m)^[^\n]{1,100}\(@[A-Za-z0-9_]{1,20}\)")
_RT_PREFIX = re.compile(r"^\s*RT\s+@[A-Za-z0-9_]{1,20}\s*:\s*")
_URL = re.compile(r"https?://\S+")
_NOT_TITLE = re.compile(r"[\d\s/月日時:：\-]+")
_HAS_WORD = re.compile(r"[A-Za-zぁ-んァ-ヶ一-龥]")
# 书名号里也可能是特典 / 版本 / 角色 / 栏目名，这些不是作品题名。
# 只列实测出现过的通用词，遇到新的按同一处补，不做模糊判断。
_NOT_A_WORK = re.compile(
    r"^(?:通常版|限定版|初回版|ダウンロード版|水着ver\.?|神衣ver\.?|"
    r"参加方法|更新履歴|制作スタッフ|スタッフ|ストーリー|アフターストーリー|"
    r"イラスト|ポスター|特典|カード|タペストリー|お知らせ|告知|情報|"
    r"純愛ルート|据膳ルート|その他|注意事項)$"
)
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]")


def primary_text(ref: dict | None) -> str:
    """只留这条来源自己的正文；引用推文、URL、RT 前缀都不算它发布的事实。"""
    text = str((ref or {}).get("text") or "")
    for pattern in (_QUOTE_SEP, _QUOTE_AUTHOR):
        match = pattern.search(text)
        if match:
            text = text[:match.start()]
    text = _RT_PREFIX.sub("", text)
    text = _URL.sub(" ", text)
    return " ".join(text.split())


def _valid_title(title: str) -> bool:
    if len(title) < 2 or "#" in title or "＃" in title or not _HAS_WORD.search(title):
        return False
    if _NOT_TITLE.fullmatch(title) or _NOT_A_WORK.fullmatch(title):
        return False
    if re.search(r"\d{1,2}\s*[/月-]\s*\d{1,2}[^\n]{0,12}時", title):
        return False
    if re.search(r"(?:情報|お知らせ|更新履歴|参加方法|ゲームソフト)$", title):
        return False
    if "【" in title or "】" in title:
        return False
    if _EMOJI.search(title):
        return False
    # `Amazonギフトカード10,000円分` 这类商品/金额不是作品名。
    if re.search(r"\d[\d,]{2,}\s*(?:円|元)", title):
        return False
    return True


def title_values(text: str) -> list[str]:
    """本推正文里的作品名（归一、保序、去重），只认书名号里的显式题名。"""
    out: list[str] = []
    for match in TITLE_RE.finditer(str(text or "")):
        title = norm_title(match.group(1))
        if _valid_title(title) and title not in out:
            out.append(title)
    return out


def source_facts(refs: dict, keys: list[str] | tuple[str, ...] | set[str]) -> dict:
    """把一组来源键合成事实：text = 本推正文串接，titles = 作品名保序去重。

    `keys` 的调用方负责保序；这里不再排序，因为「最近一条在原推里写了什么」
    会影响人工核对时的阅读顺序，但**不**参与判定优先级。
    """
    texts: list[str] = []
    titles: list[str] = []
    for key in keys or ():
        ref = refs.get(key) or {}
        body = str(ref.get("origin_text") if "origin_text" in ref
                   else primary_text(ref))
        if body:
            texts.append(body)
        for title in (ref.get("origin_titles") or title_values(body)):
            if title not in titles:
                titles.append(title)
    return {"text": "\n".join(texts), "titles": titles}
