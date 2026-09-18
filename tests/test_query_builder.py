from app.core.query_builder import (
    build_where, wildcard_pattern, Condition,
    OP_EQ, OP_NEQ, OP_CONTAINS, OP_NOT_CONTAINS, OP_MATCH)


def test_eq():
    where, params = build_where([Condition("name", OP_EQ, "张三")])
    assert where == '("name" = ?)'
    assert params == ["张三"]


def test_neq_null_semantics():
    where, params = build_where([Condition("城市", OP_NEQ, "北京")])
    # 空值视为「不等于」命中（与「不包含」一致）
    assert where == '(("城市" IS NULL OR "城市" != ?))'
    assert params == ["北京"]


def test_contains_chinese():
    where, params = build_where([Condition("商品名称", OP_CONTAINS, "手机")])
    assert where == '(CAST("商品名称" AS TEXT) LIKE ? ESCAPE \'\\\')'
    assert params == ["%手机%"]


def test_not_contains_null_semantics():
    where, params = build_where([Condition("备注", OP_NOT_CONTAINS, "测试")])
    # 空值视为「不包含」命中（每个子句外层还会包一层括号用于组合）
    assert where == '(("备注" IS NULL OR CAST("备注" AS TEXT) NOT LIKE ? ESCAPE \'\\\'))'
    assert params == ["%测试%"]


def test_like_wildcard_escaped():
    _where, params = build_where([Condition("a", OP_CONTAINS, "100%")])
    assert params == ["%100\\%%"]
    _where, params = build_where([Condition("a", OP_CONTAINS, "a_b")])
    assert params == ["%a\\_b%"]
    _where, params = build_where([Condition("a", OP_CONTAINS, "x\\y")])
    assert params == ["%x\\\\y%"]


def test_multi_condition_and_or():
    conds = [Condition("a", OP_EQ, "1"), Condition("b", OP_CONTAINS, "x")]
    where, params = build_where(conds, "AND")
    assert where == '("a" = ?) AND (CAST("b" AS TEXT) LIKE ? ESCAPE \'\\\')'
    assert params == ["1", "%x%"]
    where, _ = build_where(conds, "OR")
    assert where == '("a" = ?) OR (CAST("b" AS TEXT) LIKE ? ESCAPE \'\\\')'


def test_empty_conditions():
    assert build_where([]) == ("", [])


def test_wildcard_pattern():
    assert wildcard_pattern("手机*") == "手机%"      # 前缀
    assert wildcard_pattern("*壳") == "%壳"          # 后缀
    assert wildcard_pattern("机*盘") == "机%盘"      # 中间
    assert wildcard_pattern("手机?") == "手机_"      # 单字符
    assert wildcard_pattern("手机") == "%手机%"      # 无通配符按包含
    assert wildcard_pattern("100%*") == "100\\%%"    # 字面 % 转义 + 通配
    assert wildcard_pattern("a_b*") == "a\\_b%"      # 字面 _ 转义


def test_match_sql():
    where, params = build_where([Condition("商品名称", OP_MATCH, "手机*")])
    assert where == '(CAST("商品名称" AS TEXT) LIKE ? ESCAPE \'\\\')'
    assert params == ["手机%"]


def test_unknown_operator():
    import pytest
    with pytest.raises(ValueError):
        build_where([Condition("a", "gt", "1")])
