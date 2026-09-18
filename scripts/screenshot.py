#!/usr/bin/env python3
"""生成界面截图：选中子表的数据视图 + 搜索结果视图，保存到 output/。"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.ui.main_window import MainWindow  # noqa: E402


def main():
    app = QApplication([])
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    db = ROOT / "output" / "demo.db"
    if not db.exists():
        print("缺少 output/demo.db（先运行 make_samples + cli convert）")
        return
    win.open_db(str(db))

    shots = []

    def step_select():
        # 范围只留「订单表」并选中它 → 打开 订单表·全部 数据页
        tree = win.catalog
        for i in range(tree.topLevelItemCount()):
            g = tree.topLevelItem(i)
            for j in range(g.childCount()):
                child = g.child(j)
                if child.text(0) == "客户表":
                    child.setCheckState(0, Qt.Unchecked)
                elif child.text(0) == "订单表":
                    tree.setCurrentItem(child)
        QTimer.singleShot(500, step_search)

    def step_search():
        entry = win.cond_rows[0]
        entry["col"].setCurrentText("商品名称")
        entry["op"].setCurrentIndex(entry["op"].findData("contains"))
        entry["value"].setText("手机")
        win._do_search()
        QTimer.singleShot(600, step_shoot)

    def step_shoot():
        for i in range(win.tabs.count()):
            if win.tabs.tabText(i) == "订单表·全部":
                win.tabs.setCurrentIndex(i)
                break
        win.grab().save(str(ROOT / "output" / "截图-选中表.png"))
        shots.append("output/截图-选中表.png")
        win.tabs.setCurrentIndex(win.tabs.count() - 1)
        win.grab().save(str(ROOT / "output" / "截图-搜索结果.png"))
        shots.append("output/截图-搜索结果.png")
        app.quit()

    QTimer.singleShot(600, step_select)
    QTimer.singleShot(15000, app.quit)  # 兜底退出
    app.exec()
    print("已生成：" + "、".join(shots))


if __name__ == "__main__":
    main()
