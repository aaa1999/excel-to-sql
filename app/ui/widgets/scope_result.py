"""范围搜索结果视图：上方按子表汇总命中数，下方联动显示选中子表的命中明细。"""
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

from app.core import db_browser
from app.ui.widgets.data_table import DataTableWidget


class ScopeResultWidget(QWidget):
    def __init__(self, conn, tables, conditions, combine="AND",
                 inverse=False, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.tables = list(tables)
        self.conditions = list(conditions)
        self.combine = combine

        res = db_browser.search_totals(conn, self.tables, conditions, combine)
        hit_tables = [h for h in res["hits"] if h["total"] > 0]
        total_hits = sum(h["total"] for h in hit_tables)
        skipped_note = ("，%d 张缺少条件列已跳过" % len(res["skipped"])
                        if res["skipped"] else "")

        self.head = QLabel(
            "范围：%d 张%s子表 · 命中 %d 行，分布在 %d 张子表%s · 耗时 %.1f ms"
            % (len(self.tables), "反向（未勾选）" if inverse else "勾选",
               total_hits, len(hit_tables), skipped_note,
               res["elapsed"] * 1000))
        self.head.setWordWrap(True)

        self.summary = QTableWidget()
        self.summary.setColumnCount(2)
        self.summary.setHorizontalHeaderLabels(["子表", "命中行数"])
        self.summary.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.summary.setSelectionMode(QAbstractItemView.SingleSelection)
        self.summary.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.summary.setRowCount(len(hit_tables))
        for i, h in enumerate(hit_tables):
            self.summary.setItem(i, 0, QTableWidgetItem(h["table"]))
            self.summary.setItem(i, 1, QTableWidgetItem(str(h["total"])))
        self.summary.setMaximumHeight(200)
        self.summary.currentCellChanged.connect(self._show_detail)

        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(QLabel("在上方选择子表查看命中明细"))

        root = QVBoxLayout(self)
        root.addWidget(self.head)
        root.addWidget(self.summary)
        root.addWidget(QLabel("命中明细："))
        root.addWidget(self.detail_stack, 1)
        if hit_tables:
            self.summary.selectRow(0)

    def _show_detail(self, row, _col, _prev, _role):
        if row < 0:
            return
        table = self.summary.item(row, 0).text()
        cols = [name for name, _t in db_browser.table_columns(self.conn, table)]
        widget = DataTableWidget(self.conn, table, cols,
                                 self.conditions, self.combine)
        # 只保留占位页与当前明细，避免多次点击累积
        while self.detail_stack.count() > 1:
            page = self.detail_stack.widget(1)
            self.detail_stack.removeWidget(page)
            page.deleteLater()
        self.detail_stack.addWidget(widget)
        self.detail_stack.setCurrentWidget(widget)
