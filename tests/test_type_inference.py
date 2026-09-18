import datetime

from app.core.type_inference import infer_column_type, convert_value
from app.models.column_meta import TEXT, INTEGER, REAL


def test_all_int():
    assert infer_column_type([1, 2, 3]) == (INTEGER, False)
    assert infer_column_type(["1", "2"]) == (INTEGER, False)
    assert infer_column_type([2.0, 3.0]) == (INTEGER, False)  # Excel 常把整数读成 float


def test_float():
    assert infer_column_type([1.5, 2]) == (REAL, False)
    assert infer_column_type(["29.9", "0.5"]) == (REAL, False)


def test_text_and_mixed():
    assert infer_column_type(["a", "b"]) == (TEXT, False)
    assert infer_column_type([1, "a"]) == (TEXT, False)  # 混合类型降级 TEXT
    assert infer_column_type([]) == (TEXT, False)        # 空列


def test_date():
    assert infer_column_type([datetime.datetime(2026, 9, 1)]) == (TEXT, True)
    assert infer_column_type(["2026-09-01", "2026/09/02"]) == (TEXT, True)
    # 日期 + 普通文本 -> TEXT 非日期
    assert infer_column_type(["2026-09-01", "随便"]) == (TEXT, False)


def test_big_int_downgrade():
    assert infer_column_type(["12345678901234567"]) == (TEXT, False)  # > 2^53
    assert infer_column_type([12345678901234567]) == (TEXT, False)
    assert infer_column_type([1001]) == (INTEGER, False)


def test_leading_zero_stays_text():
    assert infer_column_type(["007", "008"]) == (TEXT, False)  # 前导零编号不转数字


def test_convert_integer():
    assert convert_value("12", INTEGER) == 12
    assert convert_value(12.0, INTEGER) == 12
    assert convert_value(3.5, INTEGER) is None  # 非整数转换失败


def test_convert_real_and_text():
    assert convert_value("29.9", REAL) == 29.9
    assert convert_value("abc", REAL) is None
    assert convert_value(29.9, TEXT) == "29.9"
    assert convert_value(123.0, TEXT) == "123"  # 整数浮点去掉 .0


def test_convert_date_iso():
    assert convert_value(datetime.datetime(2026, 9, 1, 10, 0, 0), TEXT, True) == "2026-09-01 10:00:00"
    assert convert_value(datetime.datetime(2026, 9, 2), TEXT, True) == "2026-09-02"
    assert convert_value("2026/09/03", TEXT, True) == "2026-09-03"
    assert convert_value("不是日期", TEXT, True) is None


def test_convert_empty():
    assert convert_value(None, TEXT) is None
    assert convert_value("", INTEGER) is None
    assert convert_value("   ", TEXT) is None
