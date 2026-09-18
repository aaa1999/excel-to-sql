#!/usr/bin/env python3
"""GUI 冒烟测试（离屏）：主窗口 + 目录树 + 范围搜索 + 拖动换组。

运行：QT_QPA_PLATFORM=offscreen python scripts/smoke_gui.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.core import library  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402


def main():
    app = QApplication([])
    win = MainWindow()
    win.show()

    db = ROOT / "output" / "demo.db"
    if not db.exists():
        print("跳过：output/demo.db 不存在（先运行 make_samples + cli convert）")
        return
    win.open_db(str(db))
    print("目录树:", library.list_tree(win.conn))
    print("勾选范围:", win.catalog.checked_tables())

    # 选中第一张子表 → 打开「表·全部」标签页
    group = win.catalog.topLevelItem(0)
    child = group.child(0)
    win.catalog.setCurrentItem(child)
    print("首表标签页:", win.tabs.tabText(0))

    # 跨表预检：订单表/客户表结构不一致 → 拒绝跨表查找（核心函数直接验证）
    from app.core.db_browser import check_same_structure
    ok, ref, offenders = check_same_structure(win.conn, ["订单表", "客户表"])
    assert not ok and [t for t, _s in offenders] == ["客户表"]
    print("结构预检（异构范围应拒绝）: ok=%s offenders=%s"
          % (ok, [t for t, _s in offenders]))

    # 取消勾选客户表 → 范围只剩订单表（单表不受结构限制），搜索成功
    for i in range(win.catalog.topLevelItemCount()):
        group = win.catalog.topLevelItem(i)
        for j in range(group.childCount()):
            child = group.child(j)
            if child.text(0) == "客户表":
                child.setCheckState(0, Qt.Unchecked)
    entry = win.cond_rows[0]
    entry["col"].setCurrentText("商品名称")
    entry["op"].setCurrentIndex(entry["op"].findData("contains"))
    entry["value"].setText("手机")
    win._do_search()
    last = win.tabs.widget(win.tabs.count() - 1)
    print("搜索标签页:", win.tabs.tabText(win.tabs.count() - 1))
    print("汇总:", last.head.text())
    assert "命中 3 行" in last.head.text(), "单表范围搜索命中数不符合预期"
    assert "1 张子表" in last.head.text()

    # 拖动换组：把第一张子表移到新大表（调用与 dropEvent 相同的槽）
    table = win.catalog.table_of(win.catalog.currentItem())
    win._on_table_moved(table, "测试大表")
    tree = dict(library.list_tree(win.conn))
    assert table in tree.get("测试大表", []), "拖动换组未生效"
    print("拖动换组后目录:", library.list_tree(win.conn))

    win.close()
    print("GUI 冒烟测试通过 ✔")


if __name__ == "__main__":
    main()
