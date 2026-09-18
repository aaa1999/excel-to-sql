"""读库：表列表、分页取数、命中计数、结果导出（xlsx / csv）。"""
import csv
import re
import time

from app.core.query_builder import (
    build_where, split_values, Condition, OP_EQ, OP_NEQ)

PAGE_SIZE = 100


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def list_tables(conn):
    """数据表列表（排除 sqlite 内部表与 lib_* 目录表）。"""
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "AND name NOT LIKE 'lib_%' ORDER BY name")]


def table_columns(conn, table):
    """[(列名, 类型)]，按建表顺序。"""
    return [(r[1], r[2]) for r in conn.execute("PRAGMA table_info(%s)" % _quote(table))]


def row_count(conn, table):
    return conn.execute("SELECT COUNT(*) FROM %s" % _quote(table)).fetchone()[0]


def _adapt_eq_value(conn, table, condition):
    """「等于 / 不等于」在数值列上自动按数值比较（如 订单号 = 1002）。

    多值（逗号分隔）逐个转换后回拼。
    """
    if condition.op not in (OP_EQ, OP_NEQ):
        return condition.value
    for name, ctype in table_columns(conn, table):
        if name == condition.column and ctype in ("INTEGER", "REAL"):
            out = []
            for v in split_values(condition.value):
                try:
                    out.append(str(int(v) if ctype == "INTEGER" else float(v)))
                except ValueError:
                    out.append(v)  # 非数值字面量，按原值比较
            return ",".join(out)
    return condition.value


def search(conn, table, conditions, combine="AND", page=1, page_size=PAGE_SIZE):
    """执行搜索，返回 {columns, rows, total, page, page_size, elapsed}。"""
    conds = [Condition(c.column, c.op, _adapt_eq_value(conn, table, c))
             for c in conditions]
    where, params = build_where(conds, combine)
    cols = [name for name, _t in table_columns(conn, table)]
    base = "FROM %s%s" % (_quote(table), " WHERE %s" % where if where else "")

    start = time.perf_counter()
    total = conn.execute("SELECT COUNT(*) %s" % base, params).fetchone()[0]
    offset = max(page - 1, 0) * page_size
    rows = conn.execute(
        "SELECT * %s LIMIT ? OFFSET ?" % base, tuple(params) + (page_size, offset)
    ).fetchall()
    return {"columns": cols, "rows": rows, "total": total,
            "page": page, "page_size": page_size,
            "elapsed": time.perf_counter() - start}


def table_structure(conn, table):
    """表头结构：(列名, 类型) 按建表顺序。"""
    return tuple(table_columns(conn, table))


def check_same_structure(conn, tables):
    """跨表查找预检：所有表的表头结构（列名+类型，按序）是否一致。

    返回 (ok, 参考表名, offenders)；offenders = [(表名, 该表结构)]，
    为与第一张表不一致者。单表恒为一致。
    """
    if len(tables) <= 1:
        return True, (tables[0] if tables else ""), []
    ref_struct = table_structure(conn, tables[0])
    offenders = [(t, table_structure(conn, t)) for t in tables[1:]
                 if table_structure(conn, t) != ref_struct]
    return not offenders, tables[0], offenders


def search_totals(conn, tables, conditions, combine="AND"):
    """跨表搜索：返回每张表的命中数。

    调用方应先用 check_same_structure 预检结构一致；
    此处对条件列缺失的表做防御性跳过（记入 skipped）。
    返回 {"hits": [{"table", "total"}...], "skipped": [表名...], "elapsed": 秒}
    """
    start = time.perf_counter()
    hits, skipped = [], []
    for t in tables:
        cols = {name for name, _t in table_columns(conn, t)}
        if not all(c.column in cols for c in conditions):
            skipped.append(t)
            continue
        conds = [Condition(c.column, c.op, _adapt_eq_value(conn, t, c))
                 for c in conditions]
        where, params = build_where(conds, combine)
        base = "FROM %s%s" % (_quote(t), " WHERE %s" % where if where else "")
        total = conn.execute("SELECT COUNT(*) %s" % base, params).fetchone()[0]
        hits.append({"table": t, "total": total})
    return {"hits": hits, "skipped": skipped,
            "elapsed": time.perf_counter() - start}


def _sheet_title(name):
    cleaned = re.sub(r"[:\\/?*\[\]]", "_", str(name))[:31].strip()
    return cleaned or "Sheet1"


def export(conn, table, conditions=None, combine="AND", path=None):
    """导出整表（或搜索结果）为 xlsx / csv（按扩展名判断），返回导出行数。

    csv 使用 utf-8-sig（带 BOM），双平台用 Excel 打开不乱码。
    """
    conds = [Condition(c.column, c.op, _adapt_eq_value(conn, table, c))
             for c in (conditions or [])]
    where, params = build_where(conds, combine)
    cols = [name for name, _t in table_columns(conn, table)]
    base = "FROM %s%s" % (_quote(table), " WHERE %s" % where if where else "")
    cur = conn.execute("SELECT * %s" % base, params)

    path = str(path)
    count = 0
    if path.lower().endswith(".csv"):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            for row in cur:
                writer.writerow(["" if v is None else v for v in row])
                count += 1
    else:  # 默认 xlsx，流式写出，内存占用与行数无关
        from openpyxl import Workbook
        wb = Workbook(write_only=True)
        ws = wb.create_sheet(_sheet_title(table))
        ws.append(cols)
        for row in cur:
            ws.append(list(row))
            count += 1
        wb.save(path)
    return count
