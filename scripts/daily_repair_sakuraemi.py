"""一次性订正：佐倉江美 的账号是 @sakuraemi2，不是 girlscreationpr。

用户 2026-11-06 裁决：`girlscreationpr` 是《ガールズクリエイション》的广告/PR 号，
只是佐倉江美曾经转发过，不属于声优，不能并进「声优的链接捆绑」。名单里它原来被
写成 `name=佐倉江美, role=main`，于是 `daily/build.py` 按 name 合并时把广告号选成
行首、`@sakuraemi2` 反而落到 `via` —— 已发布页面上「佐倉江美」四个字链到了广告号。

本脚本只改**身份字段**：

    report.json      accounts[]、people[].handle、people[].via
    report.ja.json   people[].handle（Ci-en 出口的人名链接）
    out/<期号>/...   工作区副本，避免重跑 apply / ja 时把旧号写回去

不改文案、不改 sources、不改数组顺序、不改期号、不碰抓取原始 jsonl / generate.json。
改之前会把「非身份字段」抽成骨架逐字比对，改之后再验一遍：全库不许再出现
girlscreationpr，人名、via 自链、中/日文版 handle 对齐都要成立。

    python scripts/daily_repair_sakuraemi.py --check
    python scripts/daily_repair_sakuraemi.py --apply
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from daily.roster import Roster  # noqa: E402

DATA = ROOT / "data" / "daily"
OUT = ROOT / "out"

OLD = "girlscreationpr"
NEW = "sakuraemi2"


class RepairError(Exception):
    pass


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(data: dict) -> str:
    # 与 src/pages/daily/[id].json.ts 的 JSON.stringify(..., null, 2) + '\n' 对齐，
    # 也和 daily_repair_language.py 的写法一致（check_daily_site 要求逐字节相同）。
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _is_old(value: object) -> bool:
    return isinstance(value, str) and value.lower() == OLD


def _is_new(value: object) -> bool:
    return isinstance(value, str) and value.lower() == NEW


def patch_zh(data: dict) -> dict:
    """中文正本：广告号从 accounts 里消失，行首换成真号，via 不再自链。"""
    out = copy.deepcopy(data)

    accounts = out.get("accounts") or []
    has_new = any(_is_new(h) for h in accounts)
    rebuilt: list[str] = []
    for handle in accounts:
        if _is_old(handle):
            # 同期已抓到真号时直接丢弃广告号；否则在原位补上真号，
            # 保持名单顺序，页面上的 @提及 链接也不断。
            if not has_new:
                rebuilt.append(NEW)
                has_new = True
            continue
        rebuilt.append(handle)
    if accounts:
        out["accounts"] = rebuilt

    for person in out.get("people") or []:
        if not isinstance(person, dict):
            continue
        if _is_old(person.get("handle")):
            person["handle"] = NEW
        via = person.get("via")
        if isinstance(via, list):
            # 真号已经是行首了，再挂在 via 里就是自己链自己；广告号一律不出现。
            person["via"] = [h for h in via if not _is_old(h) and not _is_new(h)]
    return out


def patch_ja_or_answer(data: dict) -> dict:
    """日文版 / 答稿：people[] 只有 handle + summary，换 handle 就够。"""
    out = copy.deepcopy(data)
    people = out.get("people") or []
    if not isinstance(people, list):
        return out
    for person in people:
        if isinstance(person, dict) and _is_old(person.get("handle")):
            person["handle"] = NEW
    return out


def skeleton(data: dict, kind: str) -> dict:
    """把身份字段抹掉，剩下的必须逐字相同。"""
    out = copy.deepcopy(data)
    if kind == "zh":
        out.pop("accounts", None)
        for person in out.get("people") or []:
            if isinstance(person, dict):
                person.pop("handle", None)
                person.pop("via", None)
    else:
        for person in out.get("people") or []:
            if isinstance(person, dict):
                person.pop("handle", None)
    return out


def verify(before: dict, after: dict, kind: str, label: str) -> None:
    if skeleton(before, kind) != skeleton(after, kind):
        raise RepairError(f"{label}：除身份字段外还动了别的内容")
    text = json.dumps(after, ensure_ascii=False).lower()
    if OLD in text:
        raise RepairError(f"{label}：改完仍残留 {OLD}")
    b_people = before.get("people") or []
    a_people = after.get("people") or []
    if len(b_people) != len(a_people):
        raise RepairError(f"{label}：people 条数变了")
    for b, a in zip(b_people, a_people):
        if b.get("summary") != a.get("summary"):
            raise RepairError(f"{label}：summary 被改了")
        if b.get("sources") != a.get("sources"):
            raise RepairError(f"{label}：sources 被改了")
    for person in a_people:
        if _is_new(person.get("handle")) or _is_old(person.get("handle")):
            via = person.get("via") or []
            if any(_is_new(h) or _is_old(h) for h in via):
                raise RepairError(f"{label}：via 里有真号/广告号自链")


def verify_consistency(roster: Roster, overrides: dict[Path, dict] | None = None) -> list[str]:
    """全库复核：已发布正本里不再有广告号；中日两版 handle 对得上；都在名单内。

    `--check` 时还没写盘，用 overrides 传入「改完后会是什么」；`--apply` 时直接读盘。
    """
    overrides = overrides or {}
    notes: list[str] = []
    zh_reports = sorted(DATA.glob("*/report.json"))
    ja_reports = sorted(DATA.glob("*/report.ja.json"))

    def read(path: Path) -> dict:
        return overrides.get(path) or _load(path)

    if not roster.is_known(NEW):
        raise RepairError(f"名单里没有 @{NEW}，改完页面会退回裸 handle")
    if roster.account(NEW).category != "seiyuu":
        raise RepairError(f"@{NEW} 不属于声优栏目，Ci-en 出口会把它拦下来")
    if roster.is_active(OLD) or roster.account(OLD).category == "seiyuu":
        raise RepairError(f"名单里 {OLD} 仍是 active/seiyuu，必须先隔离，否则下一期又会并回来")

    for path in zh_reports + ja_reports:
        data = read(path)
        if OLD in json.dumps(data, ensure_ascii=False).lower():
            raise RepairError(f"{path.relative_to(ROOT)}：仍残留 {OLD}")
        # 其余 handle 是否都在名单里是历史遗留问题，不是这次订正的范围，
        # 不在名单里的号站点本来就会退回裸 @handle（roster.ts 的既有退化行为）。
        for person in data.get("people") or []:
            if not str(person.get("handle") or "").strip():
                raise RepairError(f"{path.relative_to(ROOT)}：people 里有空 handle")

    for ja in ja_reports:
        zh_path = ja.parent / "report.json"
        if not zh_path.exists():
            continue
        zh_handles = [p.get("handle") for p in read(zh_path).get("people") or []]
        ja_handles = [p.get("handle") for p in read(ja).get("people") or []]
        missing = [h for h in ja_handles if h not in zh_handles]
        if missing:
            raise RepairError(f"{ja.relative_to(ROOT)}：日文版 handle 不在中文正本里：{missing}")
        # 「Ci-en 只收声优」由 check_daily_site.py 对 .ja.txt 出口把关；
        # report.ja.json 在合并名单时代还留着厂商号，这里不重复裁决。

    notes.append(f"{len(zh_reports)} 期中文正本 + {len(ja_reports)} 期日文正本："
                 f"无 {OLD} 残留，@{NEW} 在名单内且属声优，中日版 handle 对齐")
    return notes


def workspace_targets(issue_id: str) -> list[tuple[Path, str]]:
    """工作区里可能被重新 apply / ja 的副本；不存在就跳过。原始数据（jsonl /
    generate.json）是取证材料，故意不动。"""
    folder = OUT / issue_id
    return [
        (folder / "report.json", "zh"),
        (folder / "report.ja.json", "ja"),
        (folder / "answer" / "all.json", "answer"),
    ]


def run(*, apply: bool) -> int:
    roster = Roster.load()
    changed: list[str] = []
    pending: list[tuple[Path, dict, str]] = []

    for path in sorted(DATA.glob("*/report.json")):
        before = _load(path)
        if OLD not in json.dumps(before, ensure_ascii=False).lower():
            continue
        after = patch_zh(before)
        verify(before, after, "zh", str(path.relative_to(ROOT)))
        pending.append((path, after, "zh"))
        changed.append(path.parent.name)

    for path in sorted(DATA.glob("*/report.ja.json")):
        before = _load(path)
        if OLD not in json.dumps(before, ensure_ascii=False).lower():
            continue
        after = patch_ja_or_answer(before)
        verify(before, after, "ja", str(path.relative_to(ROOT)))
        pending.append((path, after, "ja"))

    print(f"发布正本：{len(pending)} 份待订正（{len(changed)} 期中文版 + "
          f"{len(pending) - len(changed)} 期日文版）")

    # 工作区副本：只有内容确实不同才算待同步，避免 --check 虚报。
    ws_pending: list[tuple[Path, dict, str]] = []
    for issue_id in changed:
        for path, kind in workspace_targets(issue_id):
            if not path.exists():
                continue
            before = _load(path)
            if OLD not in json.dumps(before, ensure_ascii=False).lower():
                continue
            after = patch_zh(before) if kind == "zh" else patch_ja_or_answer(before)
            verify(before, after, "zh" if kind == "zh" else "ja", str(path.relative_to(ROOT)))
            ws_pending.append((path, after, kind))
    print(f"工作区副本：{len(ws_pending)} 份待同步（其余不存在或已一致）")

    if apply:
        for path, data, _kind in pending + ws_pending:
            path.write_text(_dump(data), encoding="utf-8", newline="\n")
        print(f"已写入 {len(pending) + len(ws_pending)} 份")

    overrides = None if apply else {path: data for path, data, _ in pending}
    for line in verify_consistency(roster, overrides):
        print(("复核：" if apply else "预演：") + line)
    if not apply:
        print("（--check 不写盘；确认无误后跑 --apply）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只检查，不写盘")
    group.add_argument("--apply", action="store_true", help="写入订正")
    args = parser.parse_args(argv)
    try:
        return run(apply=args.apply)
    except RepairError as exc:
        print(f"订正失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
