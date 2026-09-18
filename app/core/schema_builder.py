"""表结构构建：Sheet 名/表头清洗 + 类型推断 -> TableMeta。"""
import re

from app.models.column_meta import ColumnMeta
from app.models.table_meta import TableMeta
from app.core.type_inference import infer_column_type

# 标识符仅保留：中文、字母、数字、下划线，其余替换为下划线
_ILLEGAL_RE = re.compile(r"[^0-9A-Za-z_\u4e00-\u9fff]")


def sanitize_name(raw, fallback, used, digit_prefix, max_len=64):
    """清洗标识符：替换非法字符、处理数字开头、截断、去重。

    used 为已用名集合（小写比较），函数会向其中登记新名字。
    """
    name = _ILLEGAL_RE.sub("_", str(raw if raw is not None else "").strip())
    name = name[:max_len].strip("_") or fallback
    if name[0].isdigit():
        name = digit_prefix + name
    base, candidate, i = name, name, 2
    while candidate.lower() in used:
        candidate = "%s_%d" % (base, i)
        i += 1
    used.add(candidate.lower())
    return candidate


def build_table_meta(sheet_name, header, sample_rows, header_row=True,
                     used_names=None, conflict="replace"):
    """构建 TableMeta；Sheet 完全为空时返回 None。

    header: 表头列表（header_row=False 时传 None）
    sample_rows: 采样数据行
    """
    used_names = used_names if used_names is not None else set()
    table_name = sanitize_name(sheet_name, "t_1", used_names, "t_")

    width = 0
    if header:
        width = max(width, len(header))
    for row in sample_rows:
        width = max(width, len(row))
    if width == 0:
        return None  # 空 Sheet

    columns = []
    used_cols = set()
    for idx in range(width):
        source = ""
        if header and idx < len(header) and header[idx] not in (None, ""):
            source = str(header[idx]).strip()
        name = sanitize_name(source, "col_%d" % (idx + 1), used_cols, "c_")
        col_values = [row[idx] for row in sample_rows if idx < len(row)]
        col_type, is_date = infer_column_type(col_values)
        example = ""
        for v in col_values:
            if v not in (None, ""):
                example = str(v)[:20]
                break
        columns.append(ColumnMeta(
            name=name, source_name=source or name, col_type=col_type,
            is_date=is_date, example=example, index=idx))

    return TableMeta(name=table_name, source_sheet=str(sheet_name), columns=columns,
                     header_row=header_row, conflict=conflict)
