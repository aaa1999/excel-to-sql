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

    # 范围搜索：列「手机」包含 138（订单表缺该列自动跳过；列名直接输入，
    # 模拟用户跨表搜索时手动输入其他子表的列名）
    entry = win.cond_rows[0]
    entry["col"].setCurrentText("手机")
    entry["op"].setCurrentIndex(entry["op"].findData("contains"))
    entry["value"].setText("138")
    win._do_search()
    last = win.tabs.widget(win.tabs.count() - 1)
    print("搜索标签页:", win.tabs.tabText(win.tabs.count() - 1))
    print("汇总:", last.head.text())
    assert "命中 1 行" in last.head.text(), "范围搜索命中数不符合预期"
    assert "1 张缺少条件列已跳过" in last.head.text()

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
