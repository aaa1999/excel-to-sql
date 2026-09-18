"""端到端集成：xlsx 导入 -> 类型/日期/长编号校验 -> 中文条件搜索 -> 冲突策略。"""
import sqlite3

from app.core.db_browser import list_tables, search, export
from app.core.query_builder import (
    Condition, OP_EQ, OP_NEQ, OP_CONTAINS, OP_NOT_CONTAINS, OP_MATCH)
from app.core.sqlite_writer import import_file
from app.models.table_meta import RENAME, APPEND
from app.utils.errors import SchemaMismatchError
from tests.helpers import make_sample_xlsx


def _open(tmp_path, name="t.db"):
    return sqlite3.connect(str(tmp_path / name))


def test_import_types_and_values(tmp_path):
    xlsx = make_sample_xlsx(tmp_path / "sample.xlsx")
    conn = _open(tmp_path)
    stats = import_file(conn, xlsx)

    names = list_tables(conn)
    assert "订单表" in names and "客户表" in names
    assert "草稿" not in names  # 空 Sheet 不导入

    st = next(s for s in stats if s.table == "订单表")
    assert st.rows_written == 4
    assert st.skipped_empty == 1

    # 列类型推断
    cols = {r[1]: r[2] for r in conn.execute('PRAGMA table_info("订单表")')}
    assert cols["订单号"] == "INTEGER"
    assert cols["商品名称"] == "TEXT"
    assert cols["金额"] == "REAL"
    assert cols["下单时间"] == "TEXT"   # 日期按 ISO 文本存储
    assert cols["长编号"] == "TEXT"     # 超大整数防精度丢失

    # 日期规范化为 ISO8601
    times = [r[0] for r in conn.execute(
        'SELECT "下单时间" FROM "订单表" ORDER BY "订单号"')]
    assert times == ["2026-09-01 10:00:00", "2026-09-02",
                     "2026-09-03", "2026-09-05 08:30:00"]

    # 长编号未被精度截断
    ids = {r[0] for r in conn.execute('SELECT "长编号" FROM "订单表"')}
    assert "12345678901234567" in ids

    # 数值列写入的是数值
    amounts = [r[0] for r in conn.execute('SELECT "金额" FROM "订单表" ORDER BY "订单号"')]
    assert amounts == [29.9, 9.9, 199.0, 899.5]
    conn.close()


def test_search_chinese(tmp_path):
    xlsx = make_sample_xlsx(tmp_path / "sample.xlsx")
    conn = _open(tmp_path)
    import_file(conn, xlsx)

    # 包含（中文）
    r = search(conn, "订单表", [Condition("商品名称", OP_CONTAINS, "手机")])
    assert r["total"] == 2

    # 不包含：空备注的行也算命中（1002 NULL、1003 支架、1004 新品）
    r = search(conn, "订单表", [Condition("备注", OP_NOT_CONTAINS, "测试")])
    assert r["total"] == 3

    # 等于：数值列自动按数值比较
    r = search(conn, "订单表", [Condition("订单号", OP_EQ, "1002")])
    assert r["total"] == 1
    assert r["rows"][0][1] == "手机膜"

    # 多条件 或
    r = search(conn, "订单表",
               [Condition("商品名称", OP_CONTAINS, "键盘"),
                Condition("商品名称", OP_CONTAINS, "显示器")], combine="OR")
    assert r["total"] == 2

    # 多条件 且
    r = search(conn, "订单表",
               [Condition("商品名称", OP_CONTAINS, "机"),
                Condition("备注", OP_NOT_CONTAINS, "测试")], combine="AND")
    assert r["total"] == 2  # 机械键盘（含手机支架）、显示器（新品）

    # LIKE 通配符按字面匹配
    r = search(conn, "订单表", [Condition("商品名称", OP_CONTAINS, "%")])
    assert r["total"] == 0

    # 分页
    r = search(conn, "订单表", [], page=1, page_size=2)
    assert r["total"] == 4 and len(r["rows"]) == 2
    assert r["columns"] == ["订单号", "商品名称", "金额", "下单时间", "备注", "长编号"]
    conn.close()


def test_search_neq_and_match(tmp_path):
    xlsx = make_sample_xlsx(tmp_path / "sample.xlsx")
    conn = _open(tmp_path)
    import_file(conn, xlsx)

    # 不等于（文本）：手机壳/手机膜/机械键盘/显示器 中排除手机壳
    r = search(conn, "订单表", [Condition("商品名称", OP_NEQ, "手机壳")])
    assert r["total"] == 3

    # 不等于（数值列自动按数值比较）
    r = search(conn, "订单表", [Condition("订单号", OP_NEQ, "1001")])
    assert r["total"] == 3

    # 不等于把空值视为命中：备注为空的行（1002）也计入
    r = search(conn, "订单表", [Condition("备注", OP_NEQ, "测试")])
    assert r["total"] == 3  # 1002(NULL)、1003、1004

    # 局部匹配：前缀 / 后缀 / 中间 / 单字符 / 无通配符按包含
    r = search(conn, "订单表", [Condition("商品名称", OP_MATCH, "手机*")])
    assert r["total"] == 2                       # 手机壳、手机膜
    r = search(conn, "订单表", [Condition("商品名称", OP_MATCH, "*器")])
    assert r["total"] == 1                       # 显示器
    r = search(conn, "订单表", [Condition("商品名称", OP_MATCH, "机*盘")])
    assert r["total"] == 1                       # 机械键盘
    r = search(conn, "订单表", [Condition("商品名称", OP_MATCH, "手机?")])
    assert r["total"] == 2                       # 手机壳、手机膜
    r = search(conn, "订单表", [Condition("商品名称", OP_MATCH, "手机")])
    assert r["total"] == 2
    # 通配符之间的字面 %：不匹配任何行
    r = search(conn, "订单表", [Condition("商品名称", OP_MATCH, "%*")])
    assert r["total"] == 0
    conn.close()


def test_conflict_strategies(tmp_path):
    xlsx = make_sample_xlsx(tmp_path / "sample.xlsx")

    # 默认覆盖：重复导入行数不变
    conn = _open(tmp_path)
    import_file(conn, xlsx)
    import_file(conn, xlsx)
    assert conn.execute('SELECT COUNT(*) FROM "订单表"').fetchone()[0] == 4

    # 重命名：旧表保留，新表加后缀
    import_file(conn, xlsx, conflict=RENAME)
    assert set(list_tables(conn)) >= {"订单表", "订单表_2"}
    conn.close()

    # 追加：行数翻倍
    conn2 = _open(tmp_path, "append.db")
    import_file(conn2, xlsx)
    import_file(conn2, xlsx, conflict=APPEND)
    assert conn2.execute('SELECT COUNT(*) FROM "订单表"').fetchone()[0] == 8
    conn2.close()


def test_append_schema_mismatch(tmp_path):
    import pytest
    xlsx = make_sample_xlsx(tmp_path / "sample.xlsx")
    conn = _open(tmp_path)
    import_file(conn, xlsx)
    # 构造同名但结构不一致的表
    conn.execute('DROP TABLE "订单表"')
    conn.execute('CREATE TABLE "订单表" (别的列 TEXT)')
    with pytest.raises(SchemaMismatchError):
        import_file(conn, xlsx, conflict=APPEND)
    conn.close()


def test_export(tmp_path):
    xlsx = make_sample_xlsx(tmp_path / "sample.xlsx")
    conn = _open(tmp_path)
    import_file(conn, xlsx)

    csv_path = tmp_path / "out.csv"
    n = export(conn, "订单表",
               [Condition("商品名称", OP_CONTAINS, "手机")], "AND", str(csv_path))
    assert n == 2
    content = csv_path.read_text(encoding="utf-8-sig")
    assert "商品名称" in content and "手机壳" in content

    xlsx_path = tmp_path / "out.xlsx"
    n = export(conn, "订单表", [], "AND", str(xlsx_path))
    assert n == 4
    from openpyxl import load_workbook
    wb = load_workbook(str(xlsx_path), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    assert rows[0] == ("订单号", "商品名称", "金额", "下单时间", "备注", "长编号")
    assert len(rows) == 5
    conn.close()
