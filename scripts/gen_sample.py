#!/usr/bin/env python3
"""一次性生成样例数据：用 X-rss-main 的真实账号名单（11 个 VTuber）填充。

仅用于本地预览/测试 daily_digest.py，不进生产数据流。
输出：scripts/sample_items/x.jsonl（NormalizedItem schema 对齐）。
"""
import json
from pathlib import Path

ACCOUNTS = [
    "mimoriaino", "mimo_chorion", "re_re_tsubame", "suzuka_minase",
    "asuparama40", "mirai_chiroru", "yuzuki_momoka", "momoka_vtuber",
    "hiyori_voice", "M_chipo_O", "322yui3",
]

TEMPLATES = [
    "本日の配信、ありがとうございました！次回は週末の予定です、お楽しみに。",
    "新しい歌ってみた動画をアップしました、チェックお願いします🎤",
    "今日はお絵描き配信です。みなさんのリクエストお待ちしてます！",
    "コラボ配信のお知らせ！詳細はプロフィールのリンクからご確認を。",
    "皆さんのメッセージが本当に励みになります。感謝しかないです。",
    "ゲーム実況、久しぶりにやります。一緒にワイワイ遊びましょう。",
    "衣装新調したので、次の配信でお披露目します✨",
    "ファンの皆様へ：いつも支えてくれてありがとう。これからも頑張ります。",
    "雑談配信のアーカイブを残しておきました。お風呂とか寝る前にどうぞ。",
    "来月の予定をまとめました。ライブ・撮影・リアルイベント盛りだくさん！",
]

# 每个账号的两条推文（索引错开，保证内容不同）；部分带媒体/置顶
MEDIA = {
    "mimoriaino": "https://pbs.twimg.com/media/sample_cover_mimori.png",
    "suzuka_minase": "https://pbs.twimg.com/media/sample_live_minase.png",
    "momoka_vtuber": "https://pbs.twimg.com/media/sample_outfit_momoka.png",
}
PINNED = {"322yui3": True}

items = []
for idx, acc in enumerate(ACCOUNTS):
    for k in range(2):
        t = TEMPLATES[(idx * 2 + k) % len(TEMPLATES)]
        hour = 8 + (idx + k * 5) % 13  # 分布在 08:xx ~ 20:xx UTC
        minute = (idx * 7 + k * 13) % 60
        pub = f"2026-10-24T{hour:02d}:{minute:02d}:00+00:00"
        item_id = f"t_{acc}_{k+1:02d}"
        media = []
        if acc in MEDIA and k == 0:
            media = [{"url": MEDIA[acc], "type": "image",
                      "thumbnail": MEDIA[acc]}]
        likes = 1200 + idx * 350 + k * 80
        retweets = 120 + idx * 30 + k * 10
        replies = 40 + idx * 8 + k * 3
        views = 80000 + idx * 12000 + k * 4000
        item = {
            "source_id": "x",
            "item_id": item_id,
            "title": None,
            "content": t,
            "publisher": acc,
            "canonical_url": f"https://x.com/{acc}/status/{item_id}",
            "published_at": pub,
            "published_at_raw": pub.replace("+00:00", " · Oct 24, 2026"),
            "published_precision": "second",
            "fetched_at": "2026-10-24T21:00:00+00:00",
            "media": media,
            "metadata": {
                "account": acc,
                "author_name": acc,
                "is_retweet": False,
                "retweeted_by": None,
                "is_reply": False,
                "reply_to": None,
                "is_quote": False,
                "quoted_tweet_id": None,
                "quoted_author": None,
                "quoted_text": None,
                "is_pinned": bool(k == 0 and PINNED.get(acc, False)),
                "stats": {
                    "replies": replies,
                    "retweets": retweets,
                    "likes": likes,
                    "views": views,
                },
                "provider": "nitter",
                "route": "html",
            },
        }
        items.append(item)

out = Path(__file__).resolve().parent / "sample_items" / "x.jsonl"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8") as f:
    for it in items:
        f.write(json.dumps(it, ensure_ascii=False) + "\n")

print(f"Wrote {len(items)} items -> {out}")
print("Accounts:", ", ".join(ACCOUNTS))
