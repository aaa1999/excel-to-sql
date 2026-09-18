"""统一异常体系。"""


class ExcelToSqlError(Exception):
    """基础异常。"""


class UnsupportedFileError(ExcelToSqlError):
    """不支持的文件类型 / 无法解析的编码。"""


class SchemaMismatchError(ExcelToSqlError):
    """追加导入时表结构与已有表不一致。"""
