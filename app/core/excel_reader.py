"""Excel / CSV 读取：流式逐行（read_only 模式），内存占用与文件大小无关。"""
import csv
import os
from pathlib import Path

from openpyxl import load_workbook

from app.utils.errors import UnsupportedFileError

SAMPLE_ROWS = 1000  # 类型推断采样行数上限

XLSX_EXTS = (".xlsx", ".xlsm")
CSV_EXTS = (".csv", ".tsv")


def check_file(path):
    ext = os.path.splitext(str(path))[1].lower()
    if ext in XLSX_EXTS:
        return "xlsx"
    if ext in CSV_EXTS:
        return "csv"
    raise UnsupportedFileError(
        "不支持的文件类型：%s（支持 %s）" % (path, "/".join(XLSX_EXTS + CSV_EXTS)))


def list_sheets(path):
    """列出可导入的 Sheet：[(sheet 名, 估计总行数或 None)]。

    CSV 视为单表，表名取文件名去扩展名。
    """
    kind = check_file(path)
    if kind == "csv":
        return [(Path(path).stem, None)]
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return [(name, wb[name].max_row) for name in wb.sheetnames]
    finally:
        wb.close()


def _detect_encoding(path):
    raw = Path(path).read_bytes()[:65536]
    for enc in ("utf-8-sig", "gbk"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise UnsupportedFileError("无法识别文件编码：%s（尝试过 utf-8 / gbk）" % path)


def _sniff_delimiter(path, encoding):
    if str(path).lower().endswith(".tsv"):
        return "\t"
    with open(path, encoding=encoding, newline="") as f:
        sample = f.read(8192)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        return ","


def iter_rows_raw(path, sheet=None):
    """逐行产出原始行（list，含表头行）；CSV 忽略 sheet 参数。"""
    kind = check_file(path)
    if kind == "xlsx":
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb[sheet] if sheet is not None else wb.active
            for row in ws.iter_rows(values_only=True):
                yield list(row)
        finally:
            wb.close()
    else:
        encoding = _detect_encoding(path)
        delimiter = _sniff_delimiter(path, encoding)
        with open(path, encoding=encoding, newline="") as f:
            for row in csv.reader(f, delimiter=delimiter):
                yield row


def iter_sheet_rows(path, sheet=None, header_row=True):
    """逐行产出数据行（header_row=True 时跳过首行表头）。"""
    stream = iter_rows_raw(path, sheet)
    if header_row:
        next(stream, None)
    for row in stream:
        yield row


def read_sample(path, sheet=None, header_row=True, limit=SAMPLE_ROWS):
    """读取表头与采样数据行，返回 (header, rows)。

    header_row=False 时 header 为 []，全部行都是数据。
    """
    header, rows = [], []
    for i, row in enumerate(iter_rows_raw(path, sheet)):
        if i == 0 and header_row:
            header = ["" if v is None else str(v).strip() for v in row]
            continue
        rows.append(list(row))
        if len(rows) >= limit:
            break
    return header, rows
