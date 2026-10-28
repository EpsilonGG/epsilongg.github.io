"""极简 JSON Schema 校验器（M1.4）。

只实现三份契约实际用到的关键字：
`type` / `required` / `enum` / `minLength` / `maxLength` / `pattern` /
`items` / `minItems` / `maxItems` / `properties`。

不引 `jsonschema` 的原因：整套脚本零第三方依赖，才能在任何机器的 CI 上跑起来；
而且报错可以写成中文、带上字段路径（`highlights[0].sources`），比库的默认信息有用。
schema 文件本身仍是标准 JSON Schema，以后想换库随时能换。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

# 副标题（`description`）的字数上限。**三处必须一起改**：
# `schemas/report.schema.json` 的 maxLength、`src/content.config.ts` 的 `.max()`、
# 这里。前两处是构建闸门，这一处只是让判卷的报错文案跟上
# （`tests/test_daily_schema_limits.py` 会盯着它们不许走散）。
DESCRIPTION_MAX = 70

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
}


class SchemaError(ValueError):
    """带字段路径的校验失败。`path` 形如 `$.highlights[0].sources`。"""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def load_schema(name: str) -> dict:
    """`name` 可以是 `item` / `report` / `generation`，也可以带 `.schema.json`。"""
    filename = name if name.endswith(".json") else f"{name}.schema.json"
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


def _is_type(value: Any, kind: str) -> bool:
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    if kind in _TYPE_MAP:
        return isinstance(value, _TYPE_MAP[kind])
    raise SchemaError("$", f"schema 里出现未知类型 {kind!r}")


def _check_type(value: Any, kind: str | list[str], path: str) -> None:
    kinds = kind if isinstance(kind, list) else [kind]
    if not any(_is_type(value, k) for k in kinds):
        raise SchemaError(path, f"类型应为 {'/'.join(kinds)}，实际是 {type(value).__name__}")


def validate(instance: Any, schema: dict, path: str = "$") -> None:
    """校验失败抛 `SchemaError`，成功返回 None。"""
    if "type" in schema:
        _check_type(instance, schema["type"], path)

    if "enum" in schema and instance not in schema["enum"]:
        allowed = " / ".join(json.dumps(v, ensure_ascii=False) for v in schema["enum"])
        raise SchemaError(path, f"只能是 {allowed}，实际是 {instance!r}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise SchemaError(path, f"太短（{len(instance)} < {schema['minLength']}）")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise SchemaError(path, f"太长（{len(instance)} > {schema['maxLength']}）")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            raise SchemaError(path, f"不匹配 {schema['pattern']}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                raise SchemaError(f"{path}.{key}", "缺少必填字段")
        for key, sub in (schema.get("properties") or {}).items():
            if key in instance:
                validate(instance[key], sub, f"{path}.{key}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise SchemaError(path, f"至少 {schema['minItems']} 项，实际 {len(instance)} 项")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            raise SchemaError(path, f"最多 {schema['maxItems']} 项，实际 {len(instance)} 项")
        if "items" in schema:
            for i, value in enumerate(instance):
                validate(value, schema["items"], f"{path}[{i}]")
