"""身份层：四类账号 + 转发提升 + 品牌/梯队解析。单一真源是 Galgame 名单。

* 四类：manufacturer / info / creator / other（other 含名单外）。
* 转发提升：manufacturer 或 creator 转发的推文，分类时视同该转发者类别；
  自转发（原作者＝转发者）与名单外转发者不提升。
* 一条记录可有多个来源键：按 class_priority 取唯一类别，不产生多重身份。
* 账号 handle 只从来源 URL 取；`author` 仅在整体是干净 handle 时兜底。
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import (CLASS_PRIORITY, DISPLAY_NAMES, PROMOTION_CLASSES, ROSTER,
                     read_json)

URL_HANDLE = re.compile(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status", re.I)
CLEAN_HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
# nitter/rss 路线抓到的转推不带 is_retweet 标记，只在正文/作者名里留下 `RT @xxx:`。
RT_PREFIX = re.compile(r"^\s*RT\s+@([A-Za-z0-9_]{1,15})\s*[:：]", re.I)
REPRESENTATIVE_ROLES = frozenset({"brand", "main", "sub"})


class Identity:
    def __init__(self, rules: dict):
        self.rules = rules
        roster = read_json(Path(ROSTER)).get("accounts") or []
        self.accounts = {str(a.get("handle") or "").lower(): a for a in roster}
        self.overrides = {str(k).lower(): str(v) for k, v in
                          (rules.get("account_class_overrides") or {}).items()}
        self.brands: dict[str, str] = {}
        self.names: dict[str, str] = {}
        for handle, account in self.accounts.items():
            label = str(account.get("name") or "").split("／")[0].strip()
            if label:
                self.names[handle] = label
            if account.get("role") in REPRESENTATIVE_ROLES:
                brand = str(account.get("brand") or "").strip() or label
                if brand:
                    self.brands[handle] = brand
        # 名单外账号的显示名：只给「链接标签」用，名单里的名称优先。
        # 这张表不参与分类（class_of 只看 self.accounts），所以补名字不会
        # 把账号变成 manufacturer / info，也不会牵动日报的 §19 信息号剔除。
        if DISPLAY_NAMES.is_file():
            for handle, name in (read_json(DISPLAY_NAMES).get("names") or {}).items():
                h = str(handle or "").lower().lstrip("@")
                label = str(name or "").strip()
                if h and label and h not in self.names:
                    self.names[h] = label
        self.priority = {name: i for i, name in enumerate(CLASS_PRIORITY)}

    def class_of(self, handle: str) -> str:
        h = str(handle or "").lower().lstrip("@")
        if h in self.overrides:
            return self.overrides[h]
        account = self.accounts.get(h)
        if not account:
            return "other"
        if account.get("category") == "info" or account.get("role") == "info":
            return "info"
        if account.get("category") == "manufacturer" and account.get("role") in REPRESENTATIVE_ROLES:
            return "manufacturer"
        return "other"

    def origin_handle(self, ref: dict) -> str:
        match = URL_HANDLE.search(str((ref or {}).get("url") or ""))
        if match:
            return match.group(1).lower()
        author = str((ref or {}).get("author") or "").lstrip("@").strip()
        return author.lower() if CLEAN_HANDLE.match(author) else ""

    def effective_handle(self, key: str, refs: dict) -> dict:
        ref = refs.get(key) or {}
        url_handle = ""
        match = URL_HANDLE.search(str((ref or {}).get("url") or ""))
        if match:
            url_handle = match.group(1).lower()
        origin = self.origin_handle(ref)
        by = str(ref.get("retweeted_by") or "").lstrip("@").strip().lower()
        # nitter/rss 的转推：is_retweet 为 false，但正文以 `RT @原作者:` 开头，
        # 而 URL 挂在转发者名下。这里按正文把原作者补回来，转发者取 URL 的 handle。
        rt = (RT_PREFIX.match(str(ref.get("author") or ""))
              or RT_PREFIX.match(str(ref.get("text") or "")))
        if rt:
            origin = rt.group(1).lower()
            by = by or url_handle or origin
        promoted = bool(
            (ref.get("is_retweet") or bool(rt)) and by and by != origin
            and self.class_of(by) in PROMOTION_CLASSES
        )
        handle = by if promoted else origin
        return {
            "key": key, "handle": handle, "origin": origin,
            "retweeted_by": by or None, "promoted": promoted,
            "retweet": bool(ref.get("is_retweet") or rt),
            "class": self.class_of(handle),
            "in_roster": handle in self.accounts,
        }

    def resolve(self, sources: list[str], refs: dict) -> dict:
        evidence = [self.effective_handle(k, refs) for k in sorted(set(sources or []))]
        if not evidence:
            return {"class": "other", "class_source": "no_source", "handles": [],
                    "brand": "", "display_name": "", "promoted": 0, "evidence": []}
        best = min((e["class"] for e in evidence),
                   key=lambda c: self.priority.get(c, len(self.priority)))
        chosen = [e for e in evidence if e["class"] == best]
        brand = next((self.brands.get(e["handle"], "") for e in chosen
                      if self.brands.get(e["handle"])), "")
        display = next((self.names.get(e["handle"], "") for e in chosen
                        if self.names.get(e["handle"])), "")
        return {
            "class": best,
            "class_source": "retweet_promoted" if any(e["promoted"] for e in chosen) else "origin",
            "handles": [e["handle"] for e in evidence],
            "brand": self.canonical_brand(brand),
            "display_name": display,
            "promoted": sum(1 for e in evidence if e["promoted"]),
            "evidence": evidence,
        }

    def canonical_brand(self, name: str) -> str:
        raw = str(name or "").strip()
        if not raw:
            return ""
        aliases = self.rules.get("aliases") or {}
        if raw in aliases:
            return str(aliases[raw])
        lower = raw.lower()
        for alias, canonical in aliases.items():
            if str(alias).lower() == lower:
                return str(canonical)
        return raw

    def tier_for(self, brand: str) -> int:
        canonical = self.canonical_brand(brand)
        tiers = self.rules.get("tiers") or {}
        for tier in ("1", "2"):
            names = [self.canonical_brand(x) for x in (tiers.get(tier) or [])]
            if canonical in names:
                return int(tier)
        return int(self.rules.get("default_tier") or 3)

    def tier_order(self, brand: str) -> int:
        canonical = self.canonical_brand(brand)
        names = [self.canonical_brand(x) for x in
                 ((self.rules.get("tiers") or {}).get(str(self.tier_for(brand))) or [])]
        return names.index(canonical) if canonical in names else len(names)

    def unit_rank(self, brand: str, items: int, label: str) -> tuple:
        """作品情报默认顺序：品牌梯队 → 同梯队顺位 → 小单元数降序 → 名称。"""
        return (self.tier_for(brand), self.tier_order(brand), -items, str(label))
