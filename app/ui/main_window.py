"""主窗口：数据浏览与搜索工作台。

左侧表列表 / 右侧搜索条件区 + 标签页（每张表的「全部数据」一页，
每次搜索的结果在独立的新标签页展示，可保留多个结果对比）。
"""
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QRadioButton, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout,
    QWidget)

from app.core import db_browser
from app.core.query_builder import Condition, OPERATOR_LABELS, OP_CONTAINS
from app.ui.import_wizard import ImportWizard
from app.ui.widgets.data_table import DataTableWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Excel 转 SQL — 数据浏览与搜索")
        self.resize(1280, 800)
        self.conn = None
        self.db_path = ""
        self.result_seq = 0
        self._columns_cache = {}

        toolbar = self.addToolBar("主工具栏")
        toolbar.setMovable(False)
        act_import = toolbar.addAction("导入 Excel…")
        act_import.triggered.connect(self._open_import_wizard)
        act_open = toolbar.addAction("打开数据库…")
        act_open.triggered.connect(self._open_db_dialog)
        act_sql = toolbar.addAction("导出 SQL 脚本…")
        act_sql.setEnabled(False)
        act_sql.setToolTip("生成 MySQL / PostgreSQL 方言脚本（M4 里程碑提供）")

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_placeholder())
        self.stack.addWidget(self._build_workbench())
        self.setCentralWidget(self.stack)

    # ---------- 界面构建 ----------

    def _build_placeholder(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel("点击工具栏「导入 Excel…」开始，或「打开数据库…」查看已有库")
        hint.setAlignment(Qt.AlignHCenter)
        layout.addStretch(1)
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _build_workbench(self):
        self.table_list = QListWidget()
        self.table_list.currentItemChanged.connect(self._on_table_changed)
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("表"))
        left_layout.addWidget(self.table_list)
        left = QWidget()
        left.setLayout(left_layout)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(
            lambda i: self.tabs.removeTab(i))

        right_layout = QVBoxLayout()
        right_layout.addWidget(self._build_search_box())
        right_layout.addWidget(self.tabs, 1)
        right = QWidget()
        right.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([240, 1000])
        return splitter

    def _build_search_box(self):
        self.cond_rows = []
        self.cond_area = QVBoxLayout()

        add_btn = QPushButton("＋ 添加条件")
        add_btn.clicked.connect(lambda: self._add_cond_row())
        self.and_radio = QRadioButton("且（全部满足）")
        self.and_radio.setChecked(True)
        self.or_radio = QRadioButton("或（满足其一）")
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._do_search)
        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(self._reset_search)

        bar = QHBoxLayout()
        bar.addWidget(add_btn)
        bar.addStretch(1)
        bar.addWidget(self.and_radio)
        bar.addWidget(self.or_radio)
        bar.addWidget(reset_btn)
        bar.addWidget(search_btn)

        box = QVBoxLayout()
        box.addLayout(self.cond_area)
        box.addLayout(bar)
        group = QGroupBox("条件搜索（等于 / 不等于 / 包含 / 不包含 / 局部匹配，支持中文）")
        group.setLayout(box)
        self._add_cond_row()
        return group

    # ---------- 数据库 ----------

    def open_db(self, path):
        new_conn = sqlite3.connect(path)
        self.tabs.clear()  # 释放引用旧连接的表格页
        self.result_seq = 0
        self._columns_cache = {}
        if self.conn is not None:
            self.conn.close()
        self.conn = new_conn
        self.db_path = path
        self.setWindowTitle("Excel 转 SQL — %s" % path)
        self._reload_tables()
        self.stack.setCurrentIndex(1)

    def _open_db_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "打开数据库", "", "SQLite 数据库 (*.db *.sqlite *.sqlite3)")
        if path:
            try:
                self.open_db(path)
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, "打开失败", str(e))

    def _open_import_wizard(self):
        wizard = ImportWizard(self)
        if wizard.exec() and wizard.db_path:
            self.open_db(wizard.db_path)

    def _reload_tables(self):
        self.table_list.blockSignals(True)
        self.table_list.clear()
        for name in db_browser.list_tables(self.conn):
            self.table_list.addItem(QListWidgetItem(name))
        self.table_list.blockSignals(False)
        if self.table_list.count():
            self.table_list.setCurrentRow(0)

    # ---------- 浏览与搜索 ----------

    def _current_table(self):
        item = self.table_list.currentItem()
        return item.text() if item else ""

    def _table_columns(self, table):
        if table not in self._columns_cache:
            self._columns_cache[table] = [
                name for name, _t in db_browser.table_columns(self.conn, table)]
        return self._columns_cache[table]

    def _on_table_changed(self, current, _previous):
        if current is None or self.conn is None:
            return
        table = current.text()
        cols = self._table_columns(table)
        # 搜索条件区的「列」下拉框展示当前表全部列名（含中文列名）
        for entry in self.cond_rows:
            entry["col"].clear()
            entry["col"].addItems(cols)
        # 打开/复用「表名·全部」标签页
        title = "%s·全部" % table
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == title:
                self.tabs.setCurrentIndex(i)
                return
        self.tabs.addTab(DataTableWidget(self.conn, table, cols), title)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _add_cond_row(self):
        cols = self._table_columns(self._current_table()) if self.conn else []
        row_widget = QWidget()
        col_combo = QComboBox()
        col_combo.addItems(cols)
        col_combo.setMinimumWidth(160)
        col_combo.setToolTip("列名（来自 Excel 表头）")
        op_combo = QComboBox()
        for op, label in OPERATOR_LABELS.items():
            op_combo.addItem(label, op)
        op_combo.setCurrentIndex(op_combo.findData(OP_CONTAINS))  # 默认「包含」
        value_edit = QLineEdit()
        value_edit.setPlaceholderText("输入搜索值，支持中文（局部匹配可用 * 和 ?）")
        value_edit.returnPressed.connect(self._do_search)
        del_btn = QPushButton("－")

        layout = QHBoxLayout(row_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(col_combo)
        layout.addWidget(op_combo)
        layout.addWidget(value_edit, 1)
        layout.addWidget(del_btn)

        entry = {"widget": row_widget, "col": col_combo, "op": op_combo,
                 "value": value_edit}
        self.cond_rows.append(entry)
        self.cond_area.addWidget(row_widget)

        def remove(_checked=False, e=entry):
            if len(self.cond_rows) <= 1:
                e["value"].clear()  # 至少保留一行
                return
            self.cond_rows.remove(e)
            e["widget"].deleteLater()
        del_btn.clicked.connect(remove)

    def _do_search(self):
        if self.conn is None:
            return
        table = self._current_table()
        if not table:
            QMessageBox.information(self, "提示", "请先在左侧选择一张表")
            return
        conditions = []
        for entry in self.cond_rows:
            value = entry["value"].text().strip()
            if not value:
                continue
            conditions.append(Condition(entry["col"].currentText(),
                                        entry["op"].currentData(), value))
        if not conditions:
            QMessageBox.information(self, "提示", "请至少填写一个搜索值")
            return
        combine = "AND" if self.and_radio.isChecked() else "OR"
        cols = self._table_columns(table)

        # 搜索结果固定以新标签页呈现，可保留多个结果并排对比
        self.result_seq += 1
        seq = self.result_seq
        mark = chr(0x2460 + seq - 1) if seq <= 20 else str(seq)
        widget = DataTableWidget(self.conn, table, cols, conditions, combine)
        self.tabs.addTab(widget, "搜索结果%s·%s" % (mark, table))
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _reset_search(self):
        for entry in self.cond_rows[1:]:
            entry["widget"].deleteLater()
        self.cond_rows = self.cond_rows[:1]
        if self.cond_rows:
            self.cond_rows[0]["value"].clear()
        self.and_radio.setChecked(True)

    def closeEvent(self, event):
        if self.conn is not None:
            self.conn.close()
        super().closeEvent(event)
