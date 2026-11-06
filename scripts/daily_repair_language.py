"""一次性修复：把三期被自动化写成日文的中文正本逐句改回简体中文。

事故：261030-g / 261105 / 261105-g 的模型回答整篇漂移成日文，`apply` →
`confirm` → `publish` 三层都没看出来，已发布到站点。对照表在
`README/reports/daily-language-repair-2026-11-06.json`，**只有文案字符串在表里**：

* `sources` / `handle` / `via` / `issue` / `counts` / `provenance` 等一律不进表、不改动；
* 数组顺序与 `report.json` 逐项对齐，长度不符直接拒绝，避免错位；
* 日文作品名、人名、品牌名按站内口径原样保留（只改叙述部分）。

用法：

    python scripts/daily_repair_language.py --check   # 只核对，不写
    python scripts/daily_repair_language.py --apply  # 写入正本 + 工作区副本

除了 `data/daily/<期号>/report.json`，还会同步两份**本地工作区副本**（都在 gitignore
里）：`out/<期号>/report.json` 与 `out/<期号>/answer/all.json`。不这么做，下次有人
重跑 `daily apply` / `daily publish --force`，日文回答又会把已修好的正本盖回去。

修复是**已发布正本的订正**，不是重新出稿：不重新问模型、不改来源、不改期号。
写完后必须重跑 `daily_clauses.py sync --force` 重建分句索引指纹，并重跑 build。
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import daily_lang  # noqa: E402

PATCH = ROOT / "README" / "reports" / "daily-language-repair-2026-11-06.json"
DATA = ROOT / "data" / "daily"
OUT = ROOT / "out"

DESCRIPTION_MAX = 70
PEOPLE_MAX = 60


class RepairError(RuntimeError):
    pass


def _text_of(item: object) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("text") or "")
    return ""


def _apply_list(report_value: list, patch_value: list, where: str) -> list:
    if len(report_value) != len(patch_value):
        raise RepairError(f"{where} 条数不一致：正本 {len(report_value)} / 对照表 {len(patch_value)}")
    out = copy.deepcopy(report_value)
    for i, (old, new) in enumerate(zip(report_value, patch_value)):
        if not isinstance(new, str):
            raise RepairError(f"{where}[{i}] 对照值不是字符串")
        if isinstance(old, dict):
            out[i]["text"] = new
        elif isinstance(old, str):
            out[i] = new
        else:
            raise RepairError(f"{where}[{i}] 正本形状不认识：{type(old).__name__}")
    return out


def patched(report: dict, patch: dict) -> dict:
    """返回只改了文案字段的新正本。原对象不动。"""
    out = copy.deepcopy(report)

    if patch.get("description") is not None:
        if not isinstance(patch["description"], str):
            raise RepairError("description 对照值不是字符串")
        out["description"] = patch["description"]

    for key in ("highlights", "interactions", "works", "people"):
        if key not in patch:
            continue
        if key == "people":
            values = patch[key]
            rows = out.get(key) or []
            if len(values) != len(rows):
                raise RepairError(f"people 条数不一致：正本 {len(rows)} / 对照表 {len(values)}")
            for i, (row, value) in enumerate(zip(rows, values)):
                if not isinstance(value, str):
                    raise RepairError(f"people[{i}] 对照值不是字符串")
                row["summary"] = value
        else:
            out[key] = _apply_list(out.get(key) or [], patch[key], key)
    return out


def patched_answer(answer: dict, patch: dict) -> dict:
    """同一张对照表贴到 `out/<期号>/answer/all.json` 的回答形状上。

    字段名不同（`summary` ↔ `description`），其余数组逐项对齐；`sources` 一律不动。
    """
    out = copy.deepcopy(answer)
    if patch.get("description") is not None:
        out["summary"] = patch["description"]

    for key in ("highlights", "interactions", "works", "people"):
        if key not in patch:
            continue
        values = patch[key]
        rows = out.get(key) or []
        if len(values) != len(rows):
            raise RepairError(f"answer.{key} 条数不一致：{len(rows)} / {len(values)}")
        for i, (row, value) in enumerate(zip(rows, values)):
            if not isinstance(value, str):
                raise RepairError(f"answer.{key}[{i}] 对照值不是字符串")
            if key == "people":
                if not isinstance(row, dict):
                    raise RepairError(f"answer.people[{i}] 不是对象")
                row["summary"] = value
            elif isinstance(row, dict):
                row["text"] = value
            elif isinstance(row, str):
                rows[i] = value
            else:
                raise RepairError(f"answer.{key}[{i}] 形状不认识：{type(row).__name__}")
        out[key] = rows
    return out


def verify_answer(issue: str, answer: dict, result: dict) -> None:
    bad = daily_lang.scan_answer(result)
    if bad:
        raise RepairError(
            f"{issue} 回答修复后仍有 {len(bad)} 句被判成日文，例如 "
            + "; ".join(f"{path}: {text[:40]}" for path, text in bad[:3])
        )

    def skeleton(obj: dict) -> dict:
        out = copy.deepcopy(obj)
        out["summary"] = ""
        for key in ("highlights", "interactions", "people"):
            out[key] = [
                {**row, "text" if key != "people" else "summary": ""}
                if isinstance(row, dict) else ""
                for row in (out.get(key) or [])
            ]
        out["works"] = ["" for _ in (out.get("works") or [])]
        return out

    if skeleton(answer) != skeleton(result):
        raise RepairError(f"{issue} 回答里除文案外还有别处被改动了")


def verify(issue: str, report: dict, result: dict) -> list[str]:
    """修复后的自检：形状、长度、语言。返回要打印的备注。"""
    notes: list[str] = []
    if len(result["description"]) > DESCRIPTION_MAX:
        raise RepairError(f"{issue} description {len(result['description'])} > {DESCRIPTION_MAX}")
    long_rows = [
        (p.get("handle"), len(p.get("summary") or ""))
        for p in result["people"]
        if len(p.get("summary") or "") > PEOPLE_MAX
    ]
    if long_rows:
        raise RepairError(f"{issue} people[].summary 超限（>{PEOPLE_MAX}）：{long_rows[:5]}")

    bad = daily_lang.scan_report(result)
    if bad:
        raise RepairError(
            f"{issue} 修复后仍有 {len(bad)} 句被判成日文，例如 "
            + "; ".join(f"{path}: {text[:40]}" for path, text in bad[:3])
        )

    # 除了文案，一个字节都不许变：把文案抹成空串后逐字段比较
    def skeleton(obj: dict) -> dict:
        out = copy.deepcopy(obj)
        out["description"] = ""
        for key in ("highlights", "interactions", "works"):
            rows = out.get(key) or []
            out[key] = [
                ({**row, "text": ""} if isinstance(row, dict) else "") for row in rows
            ]
        for row in out.get("people") or []:
            row["summary"] = ""
        return out

    if skeleton(report) != skeleton(result):
        raise RepairError(f"{issue} 除文案外还有别处被改动了——修复必须只改字符串")
    notes.append(f"{issue}: {len(result['people'])} 行 / {len(result['works'])} 条作品，来源与结构逐字段不变")
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="日报中文文案一次性修复")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="只核对，不写文件")
    group.add_argument("--apply", action="store_true", help="写入正本")
    args = parser.parse_args(argv)

    payload = json.loads(PATCH.read_text(encoding="utf-8"))
    notes: list[str] = []
    for issue, patch in payload["issues"].items():
        path = DATA / issue / "report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        result = patched(report, patch)
        notes.extend(verify(issue, report, result))

        # 工作区副本：同一张对照表，形状分别是正本 / 回答。
        work_report = OUT / issue / "report.json"
        work_answer = OUT / issue / "answer" / "all.json"
        extra: list[tuple[Path, dict]] = []
        pending = 0
        if work_report.exists():
            current = json.loads(work_report.read_text(encoding="utf-8"))
            fixed = patched(current, patch)
            verify(issue, current, fixed)
            pending += int(current != fixed)
            extra.append((work_report, fixed))
        if work_answer.exists():
            current = json.loads(work_answer.read_text(encoding="utf-8"))
            fixed = patched_answer(current, patch)
            verify_answer(issue, current, fixed)
            pending += int(current != fixed)
            extra.append((work_answer, fixed))

        if args.apply:
            for target, data in [(path, result), *extra]:
                target.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                print(f"  ✓ 已写入 {target.relative_to(ROOT)}")
        else:
            current_bad = daily_lang.scan_report(report)
            match = report == result
            print(f"  {'✓' if match else '!'} {issue}: 正本与对照表{'一致' if match else '不一致'}"
                  f"，当前日文命中 {len(current_bad)} 句；工作区副本 {len(extra)} 份"
                  f"（{pending} 份待同步）")
    for note in notes:
        print(f"  ✓ {note}")
    print("修复校验通过" + ("" if args.apply else "（--check，未写文件）"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RepairError as exc:
        print(f"  ✗ {exc}")
        raise SystemExit(1) from None
