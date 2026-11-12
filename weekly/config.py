"""路径、常量与规则装载。

设计约定（2026-11-09 用户裁决）：
* 四类账号身份只作用于**筛选层**（准入 / 去重择一 / 走哪道筛除池）；
* 展示层固定三组，`tier_order` 按品牌梯队默认排序，账号类不参与归栏；
* 「内容相同只留最新」是重复组择一，不是全局排序键；
* 源索引保留全部来源键，不因去重而裁剪。
"""
from __future__ import annotations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
OUT = PACKAGE / "out"
EVIDENCE = OUT / "evidence"

DAILY = ROOT / "data" / "daily"
CLAUSES = ROOT / "out" / "clauses"
# B 站动态正本（2026-11-12 用户裁决：周报第二数据源）。文件名是 JST 覆盖日，
# 与 Galgame 日报期号一一对应；由 scripts/bilibili_daily.py fetch 落盘，周报只读。
BILIBILI = ROOT / "data" / "bilibili" / "galgame"
ROSTER = ROOT / "src" / "config" / "daily-roster-galgame.json"
# 名单外账号的显示名表：只给链接标签用，不参与分类，也不进日报名单。
DISPLAY_NAMES = PACKAGE / "display-names.json"
# 品牌词表 / 梯队 / 别名 / 归栏正则。2026-11-10 起由本包自带（原在 weekly_studio/，
# 那套工作台已归档到 archive/weekly_studio/）。本包不再依赖 archive 里的任何文件。
BRAND_RULES = PACKAGE / "brand_rules.json"
RULES = PACKAGE / "rules.json"

def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# 归栏三值的唯一真源是 rules.json:columns；改归栏口径只动那一行。
COLUMNS: tuple[str, ...] = tuple(read_json(RULES)["columns"])
if len(COLUMNS) != 3:
    raise RuntimeError("rules.json:columns 必须正好三组")
WORK, MOVEMENT, INDUSTRY = COLUMNS

# 展示栏目：前三栏＝新作 / 作品情报（原品牌动向并入）/ 业界动向（2026-11-10 裁决），
# 第四栏＝B站动态（2026-11-12 裁决，只收 B 站正本，不进 X 侧归栏）。
# 归栏仍按三值算（那是「为什么放这里」的证据），带新作标签的游戏整组上提到第一栏。
# 改展示顺序只动 rules.json:display_columns；三栏写法（旧回测）仍然合法。
DISPLAY_COLUMNS: tuple[str, ...] = tuple(read_json(RULES)["display_columns"])
if len(DISPLAY_COLUMNS) not in (3, 4):
    raise RuntimeError("rules.json:display_columns 必须是三栏或四栏")
NEW, WORK_VIEW, INDUSTRY_VIEW = DISPLAY_COLUMNS[:3]
BILI_VIEW = DISPLAY_COLUMNS[3] if len(DISPLAY_COLUMNS) > 3 else ""
if WORK_VIEW != WORK or INDUSTRY_VIEW != INDUSTRY:
    raise RuntimeError("display_columns 的第二、三栏必须沿用归栏名")

CLASS_PRIORITY = ("manufacturer", "creator", "info", "other")
PROMOTION_CLASSES = frozenset({"manufacturer", "creator"})
GENERATOR = "weekly/9"

# 2026-11-10 版式：栏目名仍是唯一真源，版式开关按栏目名引用，不写死字面量。
# flat                —— 该栏不输出 `#### 游戏` 小标题，整栏按品牌铺平（正式版已无此栏）
# official_first      —— 官号（manufacturer 自发布）小条目前置
# official_no_prefix  —— 官号条目不写账号名/品牌名，只写正文（品牌名已经是 `###` 中标题）
# official_space_prefix —— 官号条目写「品牌名 + 一个空格 + 正文」（已停用，保留键位）
DEFAULT_FORMAT = {
    "flat": [],
    "official_first": [WORK, MOVEMENT],
    "official_no_prefix": [WORK, MOVEMENT],
    "official_space_prefix": [],
}


def display_format(rules: dict) -> dict:
    """rules.json:display_format 覆盖默认值；非法栏目名在这里拦掉。"""
    fmt = dict(DEFAULT_FORMAT)
    for key, value in (rules.get("display_format") or {}).items():
        if key not in fmt:
            continue
        names = [str(x) for x in value if x in COLUMNS]
        fmt[key] = names
    return fmt


def write_json(path: Path, payload: object) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )


def write_text(path: Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def load_rules() -> dict:
    """新规则（rules.json）+ 品牌词表（brand_rules.json）合成一份运行时规则。

    梯队 / 别名 / 品牌词表 / 账号运营正则以 `weekly/brand_rules.json` 为唯一真源
    （2026-11-10 随正式版一起搬进本包），不复制词表；快照写进
    `out/evidence/rules-snapshot.json`。
    """
    rules = read_json(RULES)
    brand = read_json(BRAND_RULES)
    merged = dict(rules)
    merged["tiers"] = brand.get("tiers") or {}
    merged["default_tier"] = int(brand.get("default_tier") or 3)
    merged["aliases"] = brand.get("aliases") or {}
    merged["extra_brands"] = brand.get("extra_brands") or []
    merged["movement_rules"] = brand.get("movement_rules") or {}
    merged["watched_brands"] = brand.get("watched_brands") or []
    return merged
