"""条件搜索 -> 参数化 SQL。

值一律参数绑定，从根上避免 SQL 注入与中文乱码。
「不包含」对 NULL 的语义：空值视为"不包含"命中（NULL OR NOT LIKE），
与用户直觉一致（否则备注为空的行会从结果中消失）。
"""
from dataclasses import dataclass

OP_EQ = "eq"                    # 等于
OP_CONTAINS = "contains"        # 包含
OP_NOT_CONTAINS = "not_contains"  # 不包含

OPERATOR_LABELS = {OP_EQ: "等于", OP_CONTAINS: "包含", OP_NOT_CONTAINS: "不包含"}


@dataclass
class Condition:
    column: str   # 列名
    op: str       # OP_EQ / OP_CONTAINS / OP_NOT_CONTAINS
    value: str    # 搜索值（绑定参数，支持中文）


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def _like_escape(value):
    """转义 LIKE 通配符，保证「包含」是字面包含（搜 100% 不会误命中 100x）。"""
    return (value.replace("\\", "\\\\")
                 .replace("%", "\\%")
                 .replace("_", "\\_"))


def build_where(conditions, combine="AND"):
    """条件列表 -> (where 片段, 参数列表)；无条件时返回 ("", [])。"""
    clauses, params = [], []
    for c in conditions:
        col = _quote(c.column)
        if c.op == OP_EQ:
            clauses.append("%s = ?" % col)
            params.append(c.value)
        elif c.op == OP_CONTAINS:
            clauses.append("CAST(%s AS TEXT) LIKE ? ESCAPE '\\'" % col)
            params.append("%" + _like_escape(c.value) + "%")
        elif c.op == OP_NOT_CONTAINS:
            clauses.append(
                "(%s IS NULL OR CAST(%s AS TEXT) NOT LIKE ? ESCAPE '\\')" % (col, col))
            params.append("%" + _like_escape(c.value) + "%")
        else:
            raise ValueError("未知操作符：%s" % c.op)
    if not clauses:
        return "", []
    joiner = " AND " if str(combine).upper() == "AND" else " OR "
    return joiner.join("(%s)" % cl for cl in clauses), params
