"""批量写入 SQLite：流式行 -> 事务批量 INSERT，带进度回调与统计。"""
import os
import sqlite3
import time
from dataclasses import dataclass, field

from app.models.table_meta import REPLACE, RENAME, APPEND
from app.core.type_inference import convert_value
from app.utils.errors import SchemaMismatchError


@dataclass
class WriteStats:
    table: str = ""
    source_sheet: str = ""     # "文件名 › Sheet名"
    rows_written: int = 0
    skipped_empty: int = 0     # 跳过的全空行
    null_converted: int = 0    # 类型转换失败置 NULL 的单元格数
    elapsed: float = 0.0


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(cur, name):
    return cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND lower(name)=lower(?)",
        (name,)).fetchone() is not None


def prepare_table(conn, meta):
    """处理同名表冲突，返回实际写入的表名。"""
    cur = conn.cursor()
    if not _table_exists(cur, meta.name):
        cur.execute(meta.ddl())
        return meta.name

    if meta.conflict == APPEND:
        have = [r[1] for r in cur.execute("PRAGMA table_info(%s)" % _quote(meta.name))]
        want = [c.name for c in meta.included_columns]
        if have != want:
            raise SchemaMismatchError(
                "表 %s 已存在且结构与导入列不一致，无法追加。\n  现有列：%s\n  导入列：%s"
                % (meta.name, ", ".join(have), ", ".join(want)))
        return meta.name

    if meta.conflict == RENAME:
        i = 2
        while _table_exists(cur, "%s_%d" % (meta.name, i)):
            i += 1
        actual = "%s_%d" % (meta.name, i)
        cur.execute(meta.ddl(name=actual))
        return actual

    # 默认 REPLACE：DROP 后重建
    cur.execute("DROP TABLE IF EXISTS %s" % _quote(meta.name))
    cur.execute(meta.ddl())
    return meta.name


def write_table(conn, meta, rows, batch_size=1000, progress_cb=None):
    """把数据行流写入表。progress_cb(已写入行数) 在每个事务提交后回调。"""
    cols = meta.included_columns
    if not cols:
        raise ValueError("表 %s 没有任何勾选导入的列" % meta.name)

    actual = prepare_table(conn, meta)
    insert_sql = "INSERT INTO %s VALUES (%s)" % (
        _quote(actual), ",".join("?" * len(cols)))

    stats = WriteStats(table=actual, source_sheet=meta.source_sheet)
    start = time.perf_counter()
    pending = []
    written = 0

    def _flush():
        nonlocal pending, written
        if pending:
            conn.executemany(insert_sql, pending)
            conn.commit()
            written += len(pending)
            pending = []
            if progress_cb:
                progress_cb(written)

    try:
        for row in rows:
            if row is None or all(v is None or v == "" for v in row):
                stats.skipped_empty += 1
                continue
            params = []
            for c in cols:
                raw = row[c.index] if c.index < len(row) else None
                val = convert_value(raw, c.col_type, c.is_date)
                if raw not in (None, "") and val is None:
                    stats.null_converted += 1
                params.append(val)
            pending.append(tuple(params))
            if len(pending) >= batch_size:
                _flush()
        _flush()
    except Exception:
        conn.rollback()
        raise

    stats.rows_written = written
    stats.elapsed = time.perf_counter() - start
    return stats


def import_file(conn, path, sheets=None, header_row=True, conflict=REPLACE,
                progress_cb=None):
    """导入一个 Excel/CSV 文件（默认全部非空 Sheet），返回 [WriteStats]。

    sheets: 指定导入的 Sheet 名列表；None 表示全部。
    """
    from app.core.excel_reader import list_sheets, read_sample, iter_sheet_rows
    from app.core.schema_builder import build_table_meta

    path = str(path)
    # 仅在本次导入批次内去重表名；与库中已有同名表的冲突
    # 由 prepare_table 按 replace / rename / append 策略处理
    used = set()

    # 目录登记：文件（去扩展名）= 大表分组，Sheet = 子表
    from app.core.library import init_library, register_table
    init_library(conn)
    group_name = os.path.splitext(os.path.basename(path))[0]

    # 先为每个 Sheet 构建表结构（统一去重表名），再逐表流式写入
    plan = []
    for sheet, _est in list_sheets(path):
        if sheets is not None and sheet not in sheets:
            continue
        header, sample = read_sample(path, sheet, header_row=header_row)
        meta = build_table_meta(sheet, header if header_row else None, sample,
                                header_row=header_row, used_names=used,
                                conflict=conflict)
        if meta is None:
            continue  # 空 Sheet 跳过
        plan.append((sheet, meta))
        used.add(meta.name.lower())

    stats_all = []
    for sheet, meta in plan:
        rows = iter_sheet_rows(path, sheet, header_row=header_row)
        st = write_table(conn, meta, rows, progress_cb=progress_cb)
        st.source_sheet = "%s › %s" % (os.path.basename(path), sheet)
        register_table(conn, group_name, st.table)
        stats_all.append(st)
    return stats_all
