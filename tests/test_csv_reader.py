"""CSV 导入：编码嗅探（utf-8 / gbk）、分隔符嗅探、表名取文件名。"""
import sqlite3

from app.core.db_browser import search
from app.core.excel_reader import _detect_encoding
from app.core.query_builder import Condition, OP_CONTAINS
from app.core.sqlite_writer import import_file


def test_utf8_csv(tmp_path):
    p = tmp_path / "客户.csv"
    p.write_text("客户名称,城市\n张三,北京\n李四,上海\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    import_file(conn, str(p))
    r = search(conn, "客户", [Condition("城市", OP_CONTAINS, "北")])
    assert r["total"] == 1
    assert r["rows"][0][0] == "张三"
    conn.close()


def test_gbk_csv(tmp_path):
    p = tmp_path / "客户gbk.csv"
    p.write_text("客户名称,城市\n张三,北京\n李四,上海\n", encoding="gbk")
    assert _detect_encoding(str(p)) == "gbk"
    conn = sqlite3.connect(":memory:")
    import_file(conn, str(p))
    r = search(conn, "客户gbk", [Condition("客户名称", OP_CONTAINS, "张")])
    assert r["total"] == 1
    conn.close()


def test_bom_csv(tmp_path):
    p = tmp_path / "带bom.csv"
    p.write_bytes("名称,值\n甲,1\n".encode("utf-8-sig"))
    assert _detect_encoding(str(p)) == "utf-8-sig"
    conn = sqlite3.connect(":memory:")
    import_file(conn, str(p))
    # BOM 不应混入首列列名
    cols = [r[1] for r in conn.execute('PRAGMA table_info("带bom")')]
    assert cols == ["名称", "值"]
    conn.close()


def test_semicolon_delimiter(tmp_path):
    p = tmp_path / "分号.csv"
    p.write_text("名称;值\n甲;1\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    import_file(conn, str(p))
    cols = [r[1] for r in conn.execute('PRAGMA table_info("分号")')]
    assert cols == ["名称", "值"]
    conn.close()
