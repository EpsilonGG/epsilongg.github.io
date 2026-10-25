"""日报数据层（M1：架构与数据协议）。

这一层只定义「存什么」：统一内容模型、三份 JSON Schema、增量状态、版本规则、
可复现性检查。**不做筛选、不做去重、不做分类、不调模型**——那些是 M2 / M3 的事。

    cd scripts && python -m daily version
    cd scripts && python -m daily build --items-dir sample_items --date 2026-10-23
"""

__version__ = "1.0.0"

# 契约版本。只有破坏性变更才 +1，加字段不算。
SCHEMA_VERSION = 1
