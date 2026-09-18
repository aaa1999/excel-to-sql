"""目录（大表/子表）与跨表范围搜索。"""
import sqlite3

from app.core import library
from app.core.db_browser import list_tables, search_totals, check_same_structure
from app.core.query_builder import Condition, OP_CONTAINS, OP_EQ
from app.core.sqlite_writer import import_file
from app.models.table_meta import RENAME
from tests.helpers import make_sample_xlsx


def _conn_with_data(tmp_path, name="lib.db"):
    conn = sqlite3.connect(str(tmp_path / name))
    import_file(conn, make_sample_xlsx(tmp_path / (name + ".xlsx")))
    return conn


def test_import_registers_catalog(tmp_path):
    conn = _conn_with_data(tmp_path)
    tree = dict(library.list_tree(conn))
    # 大表 = 文件名（去扩展名），子表按导入顺序
    assert tree["lib.db"] == ["订单表", "客户表"]


def test_list_tables_excludes_catalog_tables(tmp_path):
    conn = _conn_with_data(tmp_path)
    names = list_tables(conn)
    assert "订单表" in names and "客户表" in names
    assert "lib_groups" not in names and "lib_sub_tables" not in names


def test_move_table(tmp_path):
    conn = _conn_with_data(tmp_path)
    library.move_table(conn, "客户表", "另一个大表")
    tree = dict(library.list_tree(conn))
    assert tree["另一个大表"] == ["客户表"]
    assert tree["lib.db"] == ["订单表"]


def test_rename_group(tmp_path):
    conn = _conn_with_data(tmp_path)
    library.rename_group(conn, "lib.db", "订单文件")
    tree = dict(library.list_tree(conn))
    assert tree["订单文件"] == ["订单表", "客户表"]

    # 重名为已有大表 → 报错
    library.ensure_group(conn, "另一个")
    import pytest
    with pytest.raises(ValueError):
        library.rename_group(conn, "订单文件", "另一个")
    # 同名 → 无操作，不报错
    library.rename_group(conn, "订单文件", "订单文件")
    # 空名 → 报错
    with pytest.raises(ValueError):
        library.rename_group(conn, "订单文件", "   ")


def test_move_kept_after_reimport(tmp_path):
    """重复导入同名表：保留用户拖动调整过的归属，且不重复登记。"""
    conn = _conn_with_data(tmp_path)
    library.move_table(conn, "客户表", "另一个大表")
    import_file(conn, str(tmp_path / "lib.db.xlsx"))  # replace 再导入
    tree = dict(library.list_tree(conn))
    assert tree["另一个大表"] == ["客户表"]
    assert library.all_tables(conn).count("客户表") == 1


def test_auto_register_legacy_db(tmp_path):
    """旧版本建的库（无目录表）：打开时自动归入「未分组」。"""
    conn = _conn_with_data(tmp_path)
    # 模拟旧库：抹掉目录再补一张孤儿表
    conn.execute("DROP TABLE lib_groups")
    conn.execute("DROP TABLE lib_sub_tables")
    conn.execute("CREATE TABLE 孤儿表 (a TEXT)")
    conn.commit()
    library.init_library(conn)
    library.auto_register(conn)
    tree = dict(library.list_tree(conn))
    assert set(tree["未分组"]) == {"客户表", "订单表", "孤儿表"}


def test_search_totals_cross_table(tmp_path):
    conn = _conn_with_data(tmp_path)
    # 客户表没有「商品名称」列 → 跳过；订单表命中 2
    res = search_totals(conn, ["订单表", "客户表"],
                        [Condition("商品名称", OP_CONTAINS, "手机")])
    hits = {h["table"]: h["total"] for h in res["hits"]}
    assert hits == {"订单表": 2}
    assert res["skipped"] == ["客户表"]

    # 严格语义：条件涉及的所有列都要在该表存在，否则跳过该表。
    # 两个条件分别属于两张表的列 → 两张表都被跳过
    res = search_totals(conn, ["订单表", "客户表"],
                        [Condition("商品名称", OP_CONTAINS, "手机"),
                         Condition("客户名称", OP_CONTAINS, "张")], combine="OR")
    assert res["hits"] == []
    assert set(res["skipped"]) == {"订单表", "客户表"}

    # 空条件 = 各表行数
    res = search_totals(conn, ["订单表", "客户表"], [])
    hits = {h["table"]: h["total"] for h in res["hits"]}
    assert hits == {"订单表": 4, "客户表": 2}


def test_search_totals_eq_numeric(tmp_path):
    conn = _conn_with_data(tmp_path)
    res = search_totals(conn, ["订单表"], [Condition("订单号", OP_EQ, "1002")])
    assert res["hits"][0]["total"] == 1


def test_check_same_structure(tmp_path):
    conn = _conn_with_data(tmp_path)

    # 单表恒为一致
    ok, ref, offenders = check_same_structure(conn, ["订单表"])
    assert ok and ref == "订单表" and offenders == []

    # 订单表 / 客户表 列不同 → 不一致
    ok, ref, offenders = check_same_structure(conn, ["订单表", "客户表"])
    assert not ok and ref == "订单表"
    assert [t for t, _s in offenders] == ["客户表"]

    # 同一文件 rename 再导入 → 订单表_2 结构与订单表一致
    import_file(conn, str(tmp_path / "lib.db.xlsx"), conflict=RENAME)
    ok, _ref, offenders = check_same_structure(conn, ["订单表", "订单表_2"])
    assert ok and offenders == []

    # 结构一致的两张表可跨表搜索，命中各自结果
    res = search_totals(conn, ["订单表", "订单表_2"],
                        [Condition("商品名称", OP_CONTAINS, "手机")])
    hits = {h["table"]: h["total"] for h in res["hits"]}
    assert hits == {"订单表": 2, "订单表_2": 2}
    assert res["skipped"] == []


def test_check_same_structure_type_mismatch(tmp_path):
    """列名相同但类型不同也视为结构不一致。"""
    conn = _conn_with_data(tmp_path)
    conn.execute(
        'CREATE TABLE "伪订单" ("订单号" TEXT, "商品名称" TEXT, "金额" TEXT, '
        '"下单时间" TEXT, "备注" TEXT, "长编号" TEXT)')
    conn.commit()
    ok, _ref, offenders = check_same_structure(conn, ["订单表", "伪订单"])
    assert not ok
    assert [t for t, _s in offenders] == ["伪订单"]
