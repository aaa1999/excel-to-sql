"""列类型推断与单元格值转换。

推断规则（采样非空值，从最宽到最窄）：
  全部为整数      -> INTEGER（存在超过 2^53 的整数时降级 TEXT，防精度丢失）
  全部为数值      -> REAL
  全部为日期/时间 -> TEXT（ISO8601，is_date=True）
  其他 / 混合     -> TEXT
"""
import datetime
import re

from app.models.column_meta import TEXT, INTEGER, REAL

INT_RE = re.compile(r"^[+-]?\d+$")
FLOAT_RE = re.compile(r"^[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?$")
SAFE_INT_MAX = 2 ** 53

DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%Y年%m月%d日",
)

CLASS_INT, CLASS_FLOAT, CLASS_DATE, CLASS_TEXT = "int", "float", "date", "text"


def parse_date(value):
    """字符串/日期值 -> datetime；无法解析返回 None。"""
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        text = value.strip()
        try:
            return datetime.datetime.fromisoformat(text)
        except ValueError:
            pass
        for fmt in DATE_FORMATS:
            try:
                return datetime.datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _classify(value):
    if isinstance(value, bool):
        return CLASS_TEXT  # 布尔按文本处理，避免 True/False 语义歧义
    if isinstance(value, int):
        return CLASS_INT
    if isinstance(value, float):
        return CLASS_INT if value.is_integer() else CLASS_FLOAT
    if isinstance(value, (datetime.datetime, datetime.date)):
        return CLASS_DATE
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return CLASS_TEXT
        if INT_RE.match(text):
            digits = text.lstrip("+-")
            if len(digits) > 1 and digits[0] == "0":
                return CLASS_TEXT  # 前导零编号（如 007）按文本保留
            return CLASS_INT
        if FLOAT_RE.match(text):
            return CLASS_FLOAT
        if parse_date(text) is not None:
            return CLASS_DATE
    return CLASS_TEXT


def _non_empty(values):
    for v in values:
        if v is None or v == "":
            continue
        if isinstance(v, str) and not v.strip():
            continue
        yield v


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip() if isinstance(value, str) else ""
    if INT_RE.match(text):
        return int(text)
    return None


def infer_column_type(values):
    """对该列采样值推断类型，返回 (col_type, is_date)。"""
    classes = {_classify(v) for v in _non_empty(values)}
    if not classes:
        return TEXT, False
    if classes == {CLASS_DATE}:
        return TEXT, True
    if classes == {CLASS_INT}:
        for v in _non_empty(values):
            i = _as_int(v)
            if i is not None and abs(i) > SAFE_INT_MAX:
                return TEXT, False  # 超大整数（如长编号）防精度丢失
        return INTEGER, False
    if classes <= {CLASS_INT, CLASS_FLOAT}:
        return REAL, False
    return TEXT, False


def convert_value(raw, col_type, is_date=False):
    """单元格原值 -> SQLite 绑定值；无法转换返回 None（由上层计为转换失败）。"""
    if raw is None or raw == "" or (isinstance(raw, str) and not raw.strip()):
        return None
    if is_date:
        d = parse_date(raw)
        if d is None:
            return None
        if (d.hour, d.minute, d.second, d.microsecond) == (0, 0, 0, 0):
            return d.date().isoformat()
        return d.isoformat(sep=" ")
    if col_type == INTEGER:
        return _as_int(raw)
    if col_type == REAL:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    # TEXT
    if isinstance(raw, float):
        return str(int(raw)) if raw.is_integer() else str(raw)
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, (datetime.datetime, datetime.date)):
        return convert_value(raw, TEXT, True)
    return str(raw)
