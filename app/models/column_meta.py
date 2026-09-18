"""列定义：导入配置中每一列的元信息。"""
from dataclasses import dataclass

TEXT = "TEXT"
INTEGER = "INTEGER"
REAL = "REAL"

# UI 下拉框可选类型（与 SQLite 类型一一对应；日期按 ISO8601 存 TEXT）
COLUMN_TYPES = (TEXT, INTEGER, REAL)


@dataclass
class ColumnMeta:
    name: str              # 清洗后的列名（库中字段名）
    source_name: str = ""  # Excel 原始表头，UI 展示用
    col_type: str = TEXT
    include: bool = True   # 是否导入该列
    is_primary_key: bool = False
    is_date: bool = False  # TEXT 存 ISO8601 日期
    example: str = ""      # 示例值，UI 展示用
    index: int = 0         # 在源表中的列序号（行数据取值用）
