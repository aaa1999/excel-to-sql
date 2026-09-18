"""条件搜索 -> 参数化 SQL。

值一律参数绑定，从根上避免 SQL 注入与中文乱码。

空值语义（与用户直觉一致，否则空值行会从结果中消失）：
  「不等于」「不包含」把 NULL 视为命中（col IS NULL OR ...）。

局部匹配（OP_MATCH）：* 匹配任意多个字符、? 匹配单个字符；
未使用通配符时自动首尾加 %，行为等同「包含」。
"""
from dataclasses import dataclass

OP_EQ = "eq"                      # 等于
OP_NEQ = "neq"                    # 不等于
OP_CONTAINS = "contains"          # 包含
OP_NOT_CONTAINS = "not_contains"  # 不包含
OP_MATCH = "match"                # 局部匹配（* / ? 通配符）

OPERATOR_LABELS = {
    OP_EQ: "等于",
    OP_NEQ: "不等于",
    OP_CONTAINS: "包含",
    OP_NOT_CONTAINS: "不包含",
    OP_MATCH: "局部匹配",
}


@dataclass
class Condition:
    column: str   # 列名
    op: str       # 见 OP_* 常量
    value: str    # 搜索值（绑定参数，支持中文）


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def _like_escape(value):
    """转义 LIKE 通配符，保证按字面匹配（搜 100% 不会误命中 100x）。"""
    return (value.replace("\\", "\\\\")
                 .replace("%", "\\%")
                 .replace("_", "\\_"))


def wildcard_pattern(value):
    """局部匹配模式 -> LIKE 参数：* -> %，? -> _，其余按字面转义。

    未使用任何通配符时，自动首尾加 %（等同「包含」）。
    """
    out = []
    for ch in value:
        if ch == "*":
            out.append("%")
        elif ch == "?":
            out.append("_")
        else:
            out.append(_like_escape(ch))
    pattern = "".join(out)
    if "%" not in pattern and "_" not in pattern:
        pattern = "%" + pattern + "%"
    return pattern


def build_where(conditions, combine="AND"):
    """条件列表 -> (where 片段, 参数列表)；无条件时返回 ("", [])。"""
    clauses, params = [], []
    for c in conditions:
        col = _quote(c.column)
        if c.op == OP_EQ:
            clauses.append("%s = ?" % col)
            params.append(c.value)
        elif c.op == OP_NEQ:
            clauses.append("(%s IS NULL OR %s != ?)" % (col, col))
            params.append(c.value)
        elif c.op == OP_CONTAINS:
            clauses.append("CAST(%s AS TEXT) LIKE ? ESCAPE '\\'" % col)
            params.append("%" + _like_escape(c.value) + "%")
        elif c.op == OP_NOT_CONTAINS:
            clauses.append(
                "(%s IS NULL OR CAST(%s AS TEXT) NOT LIKE ? ESCAPE '\\')" % (col, col))
            params.append("%" + _like_escape(c.value) + "%")
        elif c.op == OP_MATCH:
            clauses.append("CAST(%s AS TEXT) LIKE ? ESCAPE '\\'" % col)
            params.append(wildcard_pattern(c.value))
        else:
            raise ValueError("未知操作符：%s" % c.op)
    if not clauses:
        return "", []
    joiner = " AND " if str(combine).upper() == "AND" else " OR "
    return joiner.join("(%s)" % cl for cl in clauses), params
