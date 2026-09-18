"""目录管理：大表（Excel 文件）→ 子表（Sheet）的两级目录。

目录表（lib_*）与数据表存于同一个 SQLite 库；拖动子表更换大表
只改目录归属，不动数据表本身。
"""

GROUP_TABLE = "lib_groups"
SUB_TABLE = "lib_sub_tables"
DEFAULT_GROUP = "未分组"


def init_library(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS %s ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT UNIQUE NOT NULL, sort_order INTEGER DEFAULT 0)" % GROUP_TABLE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS %s ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "group_id INTEGER NOT NULL, name TEXT UNIQUE NOT NULL, "
        "sort_order INTEGER DEFAULT 0)" % SUB_TABLE)
    conn.commit()


def ensure_group(conn, name):
    row = conn.execute(
        "SELECT id FROM %s WHERE name=?" % GROUP_TABLE, (name,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute(
        "INSERT INTO %s (name) VALUES (?)" % GROUP_TABLE, (name,))
    conn.commit()
    return cur.lastrowid


def register_table(conn, group_name, table_name):
    """把子表登记到目录；同名已登记则保持原归属（保留用户拖动调整的结果）。"""
    gid = ensure_group(conn, group_name)
    exists = conn.execute(
        "SELECT 1 FROM %s WHERE name=?" % SUB_TABLE, (table_name,)).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO %s (group_id, name) VALUES (?, ?)" % SUB_TABLE,
            (gid, table_name))
        conn.commit()


def auto_register(conn):
    """把尚未登记的数据表归入默认分组（兼容旧版本建的库）。"""
    from app.core.db_browser import list_tables
    for name in list_tables(conn):
        register_table(conn, DEFAULT_GROUP, name)


def move_table(conn, table_name, new_group_name):
    """把子表移动到另一个大表（仅改目录归属，不动数据）。"""
    gid = ensure_group(conn, new_group_name)
    conn.execute(
        "UPDATE %s SET group_id=? WHERE name=?" % SUB_TABLE,
        (gid, table_name))
    conn.commit()


def list_tree(conn):
    """[(大表名, [子表名...])]，按登记顺序。"""
    rows = conn.execute(
        "SELECT g.name, t.name FROM %(g)s g JOIN %(t)s t ON t.group_id=g.id "
        "ORDER BY g.sort_order, g.id, t.sort_order, t.id"
        % {"g": GROUP_TABLE, "t": SUB_TABLE}).fetchall()
    tree = []
    index = {}
    for gname, tname in rows:
        if gname not in index:
            index[gname] = []
            tree.append((gname, index[gname]))
        index[gname].append(tname)
    return tree


def all_tables(conn):
    return [t for _g, tables in list_tree(conn) for t in tables]
