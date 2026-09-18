"""数据表格控件：分页展示 + 命中信息 + 导出。

被「全部数据」标签页与「搜索结果」标签页共用。
"""
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.core import db_browser

PAGE_SIZE = 100


class DataTableWidget(QWidget):
    def __init__(self, conn, table, columns, conditions=None, combine="AND",
                 parent=None):
        super().__init__(parent)
        self.conn = conn
        self.table = table
        self.columns = list(columns)
        self.conditions = list(conditions or [])
        self.combine = combine
        self.page = 1
        self.total_pages = 1

        self.view = QTableWidget()
        self.view.setColumnCount(len(self.columns))
        self.view.setHorizontalHeaderLabels(self.columns)
        self.view.setEditTriggers(QTableWidget.NoEditTriggers)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.view.setAlternatingRowColors(True)

        self.info = QLabel("加载中…")
        self.prev_btn = QPushButton("上一页")
        self.next_btn = QPushButton("下一页")
        self.prev_btn.clicked.connect(self._prev)
        self.next_btn.clicked.connect(self._next)
        csv_btn = QPushButton("导出 CSV")
        csv_btn.clicked.connect(lambda: self._export(".csv"))
        xlsx_btn = QPushButton("导出 Excel")
        xlsx_btn.clicked.connect(lambda: self._export(".xlsx"))

        bar = QHBoxLayout()
        bar.addWidget(self.info)
        bar.addStretch(1)
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.next_btn)
        bar.addWidget(csv_btn)
        bar.addWidget(xlsx_btn)

        root = QVBoxLayout(self)
        root.addWidget(self.view, 1)
        root.addLayout(bar)
        self.refresh(page=1)

    def refresh(self, page=1):
        res = db_browser.search(self.conn, self.table, self.conditions,
                                combine=self.combine, page=page,
                                page_size=PAGE_SIZE)
        rows = res["rows"]
        self.view.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                self.view.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
        self.page = res["page"]
        self.total_pages = max(1, -(-res["total"] // res["page_size"]))
        self.info.setText("第 %d/%d 页 · 命中 %d 行 · 耗时 %.1f ms"
                          % (self.page, self.total_pages, res["total"],
                             res["elapsed"] * 1000))
        self.prev_btn.setEnabled(self.page > 1)
        self.next_btn.setEnabled(self.page < self.total_pages)

    def _prev(self):
        self.refresh(self.page - 1)

    def _next(self):
        self.refresh(self.page + 1)

    def _export(self, ext):
        filters = {".csv": "CSV 文件 (*.csv)", ".xlsx": "Excel 文件 (*.xlsx)"}
        path, _ = QFileDialog.getSaveFileName(self, "导出结果",
                                              self.table + ext, filters[ext])
        if not path:
            return
        try:
            count = db_browser.export(self.conn, self.table, self.conditions,
                                      self.combine, path)
        except Exception as e:  # noqa: BLE001 - 导出失败需弹窗告知用户
            QMessageBox.critical(self, "导出失败", str(e))
            return
        self.info.setText("已导出 %d 行 → %s" % (count, path))
