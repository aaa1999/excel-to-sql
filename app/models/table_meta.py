"""表定义：一个 Sheet 对应一张表。"""
from dataclasses import dataclass, field
from typing import List

from .column_meta import ColumnMeta

# 同名表冲突策略
REPLACE = "replace"  # 覆盖（DROP + 重建）
RENAME = "rename"    # 重命名新表（保留旧表）
APPEND = "append"    # 追加数据（要求结构一致）


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


@dataclass
class TableMeta:
    name: str                              # 清洗后的表名
    source_sheet: str = ""                 # Excel Sheet 名
    columns: List[ColumnMeta] = field(default_factory=list)
    header_row: bool = True                # 首行是否为表头
    conflict: str = REPLACE                # replace / rename / append

    @property
    def included_columns(self):
        return [c for c in self.columns if c.include]

    def ddl(self, name=None):
        """建表语句。name 用于冲突策略为 rename 时指定实际表名。"""
        cols = []
        for c in self.included_columns:
            piece = "%s %s" % (_quote(c.name), c.col_type)
            if c.is_primary_key:
                piece += " PRIMARY KEY"
            cols.append(piece)
        return "CREATE TABLE %s (%s)" % (_quote(name or self.name), ", ".join(cols))
