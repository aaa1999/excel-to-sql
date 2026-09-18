#!/usr/bin/env python3
"""Excel 转 SQL 命令行工具（核心引擎入口；GUI 之外的自动化/测试通道）。

用法示例：
  python cli.py convert samples/订单示例.xlsx -o output/demo.db
  python cli.py tables -d output/demo.db
  python cli.py search -d output/demo.db -t 订单表 --where 商品名称~手机
  python cli.py search -d output/demo.db -t 订单表 --where 商品名称!=手机壳 --where 备注!~测试
  python cli.py search -d output/demo.db -t 订单表 --where "商品名称@手机*"
  python cli.py export -d output/demo.db -t 订单表 -o output/订单表.xlsx

条件语法：列名=值（等于）  列名!=值（不等于）  列名~值（包含）  列名!~值（不包含）
          列名@值（局部匹配，* 任意多字符、? 单字符，如 "手机*"）
多值：值内用逗号分隔（如 商品名称~手机,键盘 = 包含任一；不等于/不包含为全部排除）
"""
import argparse
import sqlite3
import sys
from pathlib import Path

from app.core.db_browser import (
    list_tables, table_columns, row_count,
    search as db_search, export as db_export)
from app.core.query_builder import (
    Condition, OP_EQ, OP_NEQ, OP_CONTAINS, OP_NOT_CONTAINS, OP_MATCH)
from app.core.sqlite_writer import import_file
from app.models.table_meta import REPLACE, RENAME, APPEND
from app.utils.errors import ExcelToSqlError


def cmd_convert(args):
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(out))
    try:
        total_rows, total_tables = 0, 0
        for file in args.files:
            print("⟳ 导入 %s" % file)
            stats = import_file(conn, file, sheets=args.sheet or None,
                                header_row=not args.no_header,
                                conflict=args.conflict)
            for st in stats:
                print("  ✅ %s → 表 %s：%d 行（跳过空行 %d，转换失败置 NULL %d，%.2fs）"
                      % (st.source_sheet, st.table, st.rows_written,
                         st.skipped_empty, st.null_converted, st.elapsed))
            total_rows += sum(s.rows_written for s in stats)
            total_tables += len(stats)
        print("完成：%d 张表 / %d 行 → %s" % (total_tables, total_rows, out))
    finally:
        conn.close()


def cmd_tables(args):
    conn = sqlite3.connect(args.db)
    try:
        names = list_tables(conn)
        if not names:
            print("（空数据库）")
            return
        for name in names:
            print("%s  %d 行 · %d 列"
                  % (name, row_count(conn, name), len(table_columns(conn, name))))
    finally:
        conn.close()


def parse_where(text):
    seps = ((OP_NOT_CONTAINS, "!~"), (OP_NEQ, "!="), (OP_CONTAINS, "~"),
            (OP_MATCH, "@"), (OP_EQ, "="))
    for op, sep in seps:
        if sep in text:
            column, _, value = text.partition(sep)
            column = column.strip()
            if not column or not value:
                break
            return Condition(column, op, value)
    raise SystemExit(
        "条件格式错误：%r（应为 列=值 / 列!=值 / 列~值 / 列!~值 / 列@通配符）" % text)


def _print_rows(columns, rows):
    shown = columns[:12]
    cell_width = 24

    def cell(v):
        return ("" if v is None else str(v))[:cell_width]

    if rows:
        widths = [max(len(str(c)), max(len(cell(r[i])) for r in rows))
                  for i, c in enumerate(shown)]
    else:
        widths = [len(str(c)) for c in shown]
    widths = [min(w, cell_width) for w in widths]

    print(" │ ".join(str(c).ljust(w) for c, w in zip(shown, widths)))
    print("─┼─".join("─" * w for w in widths))
    for r in rows:
        print(" │ ".join(cell(r[i]).ljust(w) for i, w in enumerate(widths)))


def cmd_search(args):
    conn = sqlite3.connect(args.db)
    try:
        conditions = [parse_where(w) for w in args.where or []]
        res = db_search(conn, args.table, conditions,
                        combine=args.combine, page=args.page, page_size=args.size)
        if conditions:
            sep = " 且 " if args.combine == "AND" else " 或 "
            op_names = {"eq": "=", "neq": "!=", "contains": "包含",
                        "not_contains": "不包含", "match": "局部匹配"}
            desc = sep.join("%s %s %r" % (c.column, op_names[c.op], c.value)
                            for c in conditions)
            print("搜索：%s" % desc)
        print("表 %s · 命中 %d 行 · 耗时 %.1f ms"
              % (args.table, res["total"], res["elapsed"] * 1000))
        _print_rows(res["columns"], res["rows"])
        if args.export_csv:
            db_export(conn, args.table, conditions, args.combine, args.export_csv)
            print("已导出：%s" % args.export_csv)
    finally:
        conn.close()


def cmd_export(args):
    conn = sqlite3.connect(args.db)
    try:
        conditions = [parse_where(w) for w in args.where or []]
        count = db_export(conn, args.table, conditions, args.combine, args.output)
        print("已导出 %d 行 → %s" % (count, args.output))
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="excel-to-sql", description="Excel 转 SQL 数据库（单机，SQLite）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("convert", help="Excel/CSV → SQLite 数据库")
    p.add_argument("files", nargs="+", help="Excel/CSV 文件路径（可多个）")
    p.add_argument("-o", "--output", required=True, help="输出 .db 路径")
    p.add_argument("--sheet", action="append",
                   help="仅导入指定 Sheet（可多次；默认全部非空 Sheet）")
    p.add_argument("--no-header", action="store_true", help="首行不是表头")
    p.add_argument("--conflict", choices=[REPLACE, RENAME, APPEND], default=REPLACE,
                   help="同名表策略：replace 覆盖(默认) / rename 重命名 / append 追加")
    p.set_defaults(func=cmd_convert)

    p = sub.add_parser("tables", help="列出库中的表")
    p.add_argument("-d", "--db", required=True)
    p.set_defaults(func=cmd_tables)

    p = sub.add_parser(
        "search",
        help="条件搜索：列=值(等于) 列!=值(不等于) 列~值(包含) 列!~值(不包含) 列@通配符(局部匹配)")
    p.add_argument("-d", "--db", required=True)
    p.add_argument("-t", "--table", required=True)
    p.add_argument("--where", action="append",
                   help='条件，如 "商品名称~手机"；值可逗号分隔多个；条件可多次')
    p.add_argument("--combine", choices=["AND", "OR"], default="AND",
                   help="多条件组合（默认 AND）")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--size", type=int, default=50, help="每页行数（默认 50）")
    p.add_argument("--export-csv", help="将搜索结果导出为 CSV")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("export", help="导出整表（或筛选结果）为 xlsx/csv")
    p.add_argument("-d", "--db", required=True)
    p.add_argument("-t", "--table", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--where", action="append")
    p.add_argument("--combine", choices=["AND", "OR"], default="AND")
    p.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ExcelToSqlError as e:
        sys.exit("错误：%s" % e)


if __name__ == "__main__":
    main()
