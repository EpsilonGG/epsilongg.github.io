"""版本规则（M1.6）。

`schema_version` 只在**破坏性**变更时 +1，加字段不算。
读到比本机更高的主版本直接报错退出——猜着读一个不认识的格式，
比停下来让人升级更危险。

文件名叫 `version.py` 而不是 `migrate.py`：M4.1 那个把 Markdown frontmatter
迁成 `report.json` 的工具才叫 `migrate`，两个「迁移」不是一回事——
这里是**读**的时候兼容旧版本号，那里是**一次性**换存储格式。
"""
from __future__ import annotations

from . import SCHEMA_VERSION


class VersionError(ValueError):
    pass


def read_version(obj: dict) -> int:
    if "schema_version" not in obj:
        raise VersionError("缺少 schema_version 字段")
    version = obj["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise VersionError(f"schema_version 应为整数，实际是 {version!r}")
    return version


def check(obj: dict) -> int:
    """返回版本号；不兼容时抛 `VersionError`。"""
    version = read_version(obj)
    if version > SCHEMA_VERSION:
        raise VersionError(
            f"文件是 schema_version {version}，本机只支持到 {SCHEMA_VERSION}；"
            "请先升级脚本，不要用旧代码读新格式"
        )
    return version


def migrate(obj: dict) -> dict:
    """把旧版本升到当前版本。目前只有 v1，所以只做校验。"""
    check(obj)
    return obj
