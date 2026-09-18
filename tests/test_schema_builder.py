from app.core.schema_builder import sanitize_name, build_table_meta


def test_sanitize_illegal_chars():
    used = set()
    assert sanitize_name("订单 表", "t_1", used, "t_") == "订单_表"
    assert sanitize_name("a/b-c*d", "t_1", used, "t_") == "a_b_c_d"


def test_sanitize_digit_start():
    used = set()
    assert sanitize_name("2026销量", "t_1", used, "t_") == "t_2026销量"  # 表加 t_ 前缀
    used2 = set()
    assert sanitize_name("1月", "col_1", used2, "c_") == "c_1月"        # 列加 c_ 前缀


def test_sanitize_dedup_and_empty():
    used = set()
    assert sanitize_name("名称", "col_1", used, "c_") == "名称"
    assert sanitize_name("名称", "col_2", used, "c_") == "名称_2"
    assert sanitize_name(None, "col_3", used, "c_") == "col_3"
    assert sanitize_name("###", "col_4", used, "c_") == "col_4"


def test_build_table_meta():
    meta = build_table_meta(
        "订单 表",
        header=["序号", "商品 名称", "序号"],
        sample_rows=[[1, "手机壳", 2], [2, "键盘", 3]])
    assert meta.name == "订单_表"
    names = [c.name for c in meta.columns]
    assert names == ["序号", "商品_名称", "序号_2"]
    assert [c.col_type for c in meta.columns] == ["INTEGER", "TEXT", "INTEGER"]
    assert [c.source_name for c in meta.columns] == ["序号", "商品 名称", "序号"]
    assert meta.columns[0].index == 0


def test_build_table_meta_no_header():
    meta = build_table_meta("数据", header=None,
                            sample_rows=[[1, "a"], [2, "b"]], header_row=False)
    assert [c.name for c in meta.columns] == ["col_1", "col_2"]


def test_build_table_meta_empty_sheet():
    assert build_table_meta("空表", header=[], sample_rows=[]) is None


def test_build_table_meta_dedup_table_names():
    used = {"订单表"}
    meta = build_table_meta("订单表", header=["a"], sample_rows=[[1]],
                            used_names=used)
    assert meta.name == "订单表_2"
