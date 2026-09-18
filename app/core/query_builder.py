"""条件搜索 -> 参数化 SQL。

值一律参数绑定，从根上避免 SQL 注入与中文乱码。

多值输入：一个条件的值可用逗号（半角 , / 全角 ，）分隔多个。
  等于 / 包含 / 局部匹配 多值 -> 命中任一（OR）
  不等于 / 不包含 多值       -> 全部排除 / 全部不含（AND），空值仍视为命中

空值语义（与用户直觉一致，否则空值行会从结果中消失）：
  「不等于」「不包含」把 NULL 视为命中（col IS NULL OR ...）。

局部匹配（OP_MATCH）：* 匹配任意多个字符、? 匹配单个字符；
未使用通配符时自动首尾加 %，行为等同「包含」。
"""
import re
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
    value: str    # 搜索值，支持中文；多个值用逗号分隔


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def split_values(value):
    """按半角/全角逗号拆分为多个搜索值，去掉空白项。"""
    return [v for v in (s.strip() for s in re.split(r"[,，]", str(value))) if v]


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


def _predicates(col, op, values):
    """每个值 -> (SQL 谓词列表, 参数列表)。"""
    preds, params = [], []
    for v in values:
        if op == OP_EQ:
            preds.append("%s = ?" % col)
            params.append(v)
        elif op == OP_NEQ:
            preds.append("%s != ?" % col)
            params.append(v)
        elif op == OP_CONTAINS:
            preds.append("CAST(%s AS TEXT) LIKE ? ESCAPE '\\'" % col)
            params.append("%" + _like_escape(v) + "%")
        elif op == OP_NOT_CONTAINS:
            preds.append("CAST(%s AS TEXT) NOT LIKE ? ESCAPE '\\'" % col)
            params.append("%" + _like_escape(v) + "%")
        elif op == OP_MATCH:
            preds.append("CAST(%s AS TEXT) LIKE ? ESCAPE '\\'" % col)
            params.append(wildcard_pattern(v))
        else:
            raise ValueError("未知操作符：%s" % op)
    return preds, params


def build_where(conditions, combine="AND"):
    """条件列表 -> (where 片段, 参数列表)；无条件时返回 ("", [])。

    每个条件（行）先按自身多值语义组成一个子句，条件之间再按
    combine（AND / OR）连接。
    """
    parts, params = [], []
    for c in conditions:
        values = split_values(c.value)
        if not values:
            continue
        if c.op not in OPERATOR_LABELS:
            raise ValueError("未知操作符：%s" % c.op)
        col = _quote(c.column)
        preds, p = _predicates(col, c.op, values)
        if len(preds) == 1:
            if c.op in (OP_NEQ, OP_NOT_CONTAINS):
                clause = "(%s IS NULL OR %s)" % (col, preds[0])
            else:
                clause = preds[0]
        elif c.op in (OP_EQ, OP_CONTAINS, OP_MATCH):
            clause = "(%s)" % " OR ".join(preds)  # 多值命中任一
        else:  # OP_NEQ / OP_NOT_CONTAINS：多值全部排除 / 全部不含
            clause = "(%s IS NULL OR (%s))" % (col, " AND ".join(preds))
        parts.append(clause)
        params.extend(p)
    if not parts:
        return "", []
    joiner = " AND " if str(combine).upper() == "AND" else " OR "
    return joiner.join("(%s)" % cl for cl in parts), params
