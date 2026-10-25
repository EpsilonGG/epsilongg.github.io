"""统一内容模型（M1.2）。

下游只认这里的形状，不认 X-Reader 的字段名——X-Reader 改字段只影响
`adapters/xreader.py` 一个文件。序列化时键序固定：JSON 的 diff 才有意义，
「同输入同输出」也才有意义。

字段的取舍见 `public/docs/dailyrp-projectstatus.html` §3「统一内容模型」。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .issue import JST

def item_key(source: str, native_id: str) -> str:
    """稳定身份：`source:native_id`。同一来源的同一条内容只有一个 key。"""
    return f"{source}:{native_id}"


def content_hash(text: str) -> str:
    """内容指纹。只跟文本有关，首尾空白与换行差异不影响。"""
    norm = re.sub(r"\s+", " ", (text or "").strip())
    return "sha256:" + hashlib.sha256(norm.encode("utf-8")).hexdigest()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Engagement:
    """互动数。**只给模型选材参考，不进排序键**（样例里 stats 全是空的）。"""

    likes: int = 0
    reposts: int = 0
    replies: int = 0
    views: int | None = None

    @classmethod
    def from_stats(cls, stats: dict | None) -> "Engagement":
        s = stats or {}
        return cls(
            likes=int(s.get("likes") or 0),
            reposts=int(s.get("retweets") or s.get("reposts") or 0),
            replies=int(s.get("replies") or 0),
            views=(int(s["views"]) if s.get("views") is not None else None),
        )

    def score(self) -> int:
        return self.likes + self.reposts

    def to_dict(self) -> dict:
        return {
            "likes": self.likes,
            "reposts": self.reposts,
            "replies": self.replies,
            "views": self.views,
        }


@dataclass
class Item:
    """一个标准化条目。一条内容只存一份，转发过它的人记在 `amplifiers`。"""

    key: str
    source: str
    native_id: str
    account: str
    published_at: str = ""
    precision: str = "second"
    text: str = ""
    url: str = ""
    kind: str = "post"
    reply_to: str | None = None
    quote_of: str | None = None
    repost_of: str | None = None
    amplifiers: list[str] = field(default_factory=list)
    engagement: Engagement = field(default_factory=Engagement)
    media: list[dict] = field(default_factory=list)
    content_hash: str = ""
    first_seen: str = ""
    raw_ref: str = ""
    # 原始记录，只在调试与回溯时用，不进序列化
    raw: dict = field(default_factory=dict, repr=False)

    # -- 序列化：键序固定，别改顺序 ------------------------------------
    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "source": self.source,
            "native_id": self.native_id,
            "account": self.account,
            "amplifiers": list(self.amplifiers),
            "published_at": self.published_at,
            "precision": self.precision,
            "text": self.text,
            "url": self.url,
            "kind": self.kind,
            "reply_to": self.reply_to,
            "quote_of": self.quote_of,
            "repost_of": self.repost_of,
            "engagement": self.engagement.to_dict(),
            "media": list(self.media),
            "content_hash": self.content_hash,
            "first_seen": self.first_seen,
            "raw_ref": self.raw_ref,
        }

    # -- 派生值 --------------------------------------------------------
    def published_dt(self) -> datetime | None:
        return parse_dt(self.published_at)

    def date(self) -> date | None:
        """发布时间所在的**自然日**，一律按 JST 算（M2.1 起）。

        M1 时这里取的是时间戳自带的时区（X-Reader 给 UTC），于是「一天」是
        JST 09:00 → 次日 08:59，凌晨发的推会被算到前一天。日报写的是日本声优的一天，
        分天边界只能是 JST 00:00。窗口切分见 `window.IssueWindow`。
        """
        dt = self.published_dt()
        if dt is None:
            return None
        return (dt if dt.tzinfo else dt.replace(tzinfo=JST)).astimezone(JST).date()

    def hash(self) -> str:
        """内容指纹。字段为空时现算——手搓的 `Item` 不该因为没有 hash 就绕过变更检测。"""
        return self.content_hash or content_hash(self.text)

    @classmethod
    def from_xreader(cls, raw: dict, raw_ref: str = "") -> "Item":
        meta = raw.get("metadata") or {}
        source = (raw.get("source_id") or "x").strip() or "x"
        native_id = str(raw.get("item_id") or raw.get("id") or "").strip()
        account = (
            (raw.get("publisher") or "").strip()
            or (meta.get("account") or "").strip()
            or source
        )
        text = raw.get("content") or raw.get("title") or ""
        if meta.get("is_retweet"):
            kind = "repost"
        elif meta.get("is_quote"):
            kind = "quote"
        elif meta.get("is_reply"):
            kind = "reply"
        else:
            kind = "post"
        precision = raw.get("published_precision") or "second"
        published = raw.get("published_at") or raw.get("fetched_at") or ""
        return cls(
            key=item_key(source, native_id),
            source=source,
            native_id=native_id,
            account=account,
            published_at=published,
            precision=precision if precision in ("second", "minute", "day") else "second",
            text=text,
            url=raw.get("canonical_url") or "",
            kind=kind,
            reply_to=(meta.get("reply_to") or None),
            quote_of=(meta.get("quoted_tweet_id") or None),
            repost_of=(meta.get("retweeted_by") or None),
            amplifiers=[account] if meta.get("is_retweet") else [],
            engagement=Engagement.from_stats(meta.get("stats")),
            media=list(raw.get("media") or []),
            content_hash=content_hash(text),
            first_seen=raw.get("fetched_at") or "",
            raw_ref=raw_ref,
            raw=raw,
        )


@dataclass
class Account:
    """名单里的一个人。分类是**数据**（M2 填），结构是**协议**（M1 定）。"""

    handle: str
    name: str = ""
    category: str = "other"
    active: bool = True
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "handle": self.handle,
            "name": self.name,
            "category": self.category,
            "active": self.active,
            "tags": list(self.tags),
        }


@dataclass
class Issue:
    """一期日报的身份。期号 = 发布时间 = 网址。"""

    id: str
    published_at: str
    status: str = "draft"
    confirmed_at: str | None = None
    window_start: str = ""
    window_end: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "published_at": self.published_at,
            "window": {"start": self.window_start, "end": self.window_end},
            "status": self.status,
            "confirmed_at": self.confirmed_at,
        }


@dataclass
class Claim:
    """一句写进日报的话，必须能指回条目。没有来源的句子不收（M3 校验）。"""

    text: str
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"text": self.text, "sources": list(self.sources)}


@dataclass
class Report:
    """一份日报的正本。`people` 是扁平的，每人带 `category`——
    分类视图靠 filter 得到，不另存一份（一份数据多种视图）。"""

    issue: Issue
    schema_version: int = 1
    counts: dict = field(default_factory=dict)
    description: str = ""
    highlights: list[Claim] = field(default_factory=list)
    insights: list[Claim] = field(default_factory=list)
    interactions: list[Claim] = field(default_factory=list)
    categories: list[dict] = field(default_factory=list)
    people: list[dict] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "issue": self.issue.to_dict(),
            "counts": {
                "items": int(self.counts.get("items", 0)),
                "accounts": int(self.counts.get("accounts", 0)),
                "late": int(self.counts.get("late", 0)),
                "skipped_duplicate": int(self.counts.get("skipped_duplicate", 0)),
            },
            "description": self.description,
            "highlights": [c.to_dict() for c in self.highlights],
            "insights": [c.to_dict() for c in self.insights],
            "interactions": [c.to_dict() for c in self.interactions],
            "categories": list(self.categories),
            "people": list(self.people),
            "provenance": dict(self.provenance),
        }
