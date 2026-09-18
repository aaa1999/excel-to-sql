#!/usr/bin/env python3
"""GUI 冒烟测试（离屏）：构建主窗口，打开示例库，切换表并执行一次中文搜索。

运行：QT_QPA_PLATFORM=offscreen python scripts/smoke_gui.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

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
    print("打开库：%s" % win.db_path)
    print("表数量：%d" % win.table_list.count())

    if win.table_list.count():
        win.table_list.setCurrentRow(0)
        print("首表标签页：%s（列数 %d）"
              % (win.tabs.tabText(0), win.tabs.widget(0).view.columnCount()))

        # 明确选「手机」列 +「包含」操作符（结果应出现在新标签页且命中 1 行）
        entry = win.cond_rows[0]
        entry["col"].setCurrentIndex(entry["col"].findText("手机"))
        entry["op"].setCurrentIndex(entry["op"].findData("contains"))
        entry["value"].setText("138")
        win._do_search()
        last = win.tabs.widget(win.tabs.count() - 1)
        print("搜索后标签页：%s" % win.tabs.tabText(win.tabs.count() - 1))
        print("命中信息：%s" % last.info.text())
        assert "命中 1 行" in last.info.text(), "搜索命中数不符合预期"

    win.close()
    print("GUI 冒烟测试通过 ✔")


if __name__ == "__main__":
    main()
