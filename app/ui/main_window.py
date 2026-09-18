"""主窗口：目录树（大表/子表）+ 条件搜索工作台。

- 左侧目录树：大表（Excel 文件）分组 → 子表；勾选子表 = 搜索范围（可跨大表），
  拖动子表可更换所属大表（仅改目录归属）
- 右侧：条件搜索区（可指定正向/反向范围）+ 标签页
  （每张子表的「全部数据」一页；每次搜索的范围结果一页，页内按子表汇总）
"""
import sqlite3
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QRadioButton, QSplitter,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

from app.core import db_browser, library
from app.core.query_builder import Condition, OPERATOR_LABELS, OP_CONTAINS
from app.ui.import_wizard import ImportWizard
from app.ui.widgets.catalog_tree import CatalogTree
from app.ui.widgets.data_table import DataTableWidget
from app.ui.widgets.scope_result import ScopeResultWidget

_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DB = _ROOT / "output" / "demo.db"


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
        self._reopen_last_db()

    def _reopen_last_db(self):
        """启动时自动恢复上次打开的数据库（如有）。"""
        path = QSettings("excel-to-sql", "excel-to-sql").value("last_db", "")
        if path and Path(path).exists():
            try:
                self.open_db(path)
            except Exception:  # noqa: BLE001 - 恢复失败则停在引导页
                pass

    # ---------- 界面构建 ----------

    def _build_placeholder(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(2)
        title = QLabel("尚未打开数据库")
        title.setAlignment(Qt.AlignHCenter)
        hint = QLabel("范围搜索与勾选子表需要先打开一个数据库，任选一种方式开始：")
        hint.setAlignment(Qt.AlignHCenter)

        btn_import = QPushButton("导入 Excel…（从 Excel/CSV 文件创建库）")
        btn_import.clicked.connect(self._open_import_wizard)
        btn_open = QPushButton("打开已有数据库…")
        btn_open.clicked.connect(self._open_db_dialog)
        btn_sample = QPushButton("打开示例数据库")
        btn_sample.clicked.connect(lambda: self._open_path(str(_DEMO_DB)))
        if not _DEMO_DB.exists():
            btn_sample.setEnabled(False)
            btn_sample.setToolTip("示例库不存在（output/demo.db）")

        btn_box = QVBoxLayout()
        for b in (btn_import, btn_open, btn_sample):
            b.setMaximumWidth(360)
            btn_box.addWidget(b)
        center = QHBoxLayout()
        center.addStretch(1)
        center.addLayout(btn_box)
        center.addStretch(1)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(12)
        layout.addLayout(center)
        layout.addStretch(3)
        return page

    def _open_path(self, path):
        try:
            self.open_db(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "打开失败", str(e))

    def _build_workbench(self):
        self.catalog = CatalogTree()
        self.catalog.currentItemChanged.connect(self._on_item_changed)
        self.catalog.table_moved.connect(self._on_table_moved)
        self.catalog.group_renamed.connect(self._on_group_renamed)

        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("目录（勾选子表 = 搜索范围，可拖动换组）"))

        # 批量勾选按钮：不依赖点中小复选框，一键调整范围
        btn_row = QHBoxLayout()
        btn_all = QPushButton("全选")
        btn_all.clicked.connect(self.catalog.check_all)
        btn_none = QPushButton("全不选")
        btn_none.clicked.connect(self.catalog.uncheck_all)
        btn_invert = QPushButton("反选")
        btn_invert.clicked.connect(self.catalog.invert_all)
        for b in (btn_all, btn_none, btn_invert):
            btn_row.addWidget(b)
        left_layout.addLayout(btn_row)
        left_layout.addWidget(self.catalog)
        left = QWidget()
        left.setLayout(left_layout)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(lambda i: self.tabs.removeTab(i))

        right_layout = QVBoxLayout()
        right_layout.addWidget(self._build_search_box())
        right_layout.addWidget(self.tabs, 1)
        right = QWidget()
        right.setLayout(right_layout)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([280, 1000])
        return splitter

    def _build_search_box(self):
        self.cond_rows = []
        self.cond_area = QVBoxLayout()

        add_btn = QPushButton("＋ 添加条件")
        add_btn.clicked.connect(lambda: self._add_cond_row())
        self.and_radio = QRadioButton("且（全部满足）")
        self.and_radio.setChecked(True)
        self.or_radio = QRadioButton("或（满足其一）")

        # 查找范围：勾选的子表（正向）/ 未勾选的子表（反向）
        self.scope_normal = QRadioButton("在勾选的子表中查找")
        self.scope_normal.setChecked(True)
        self.scope_inverse = QRadioButton("反向：在未勾选的子表中查找")

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
        scope_bar = QHBoxLayout()
        scope_bar.addWidget(self.scope_normal)
        scope_bar.addWidget(self.scope_inverse)
        scope_bar.addStretch(1)

        box = QVBoxLayout()
        box.addLayout(self.cond_area)
        box.addLayout(bar)
        box.addLayout(scope_bar)
        group = QGroupBox("条件搜索（等于 / 不等于 / 包含 / 不包含 / 局部匹配，支持中文）")
        group.setLayout(box)
        self._add_cond_row()
        return group

    # ---------- 数据库 ----------

    def open_db(self, path):
        new_conn = sqlite3.connect(path)
        library.init_library(new_conn)
        library.auto_register(new_conn)  # 旧库未登记的表归入“未分组”
        self.tabs.clear()
        self.result_seq = 0
        self._columns_cache = {}
        if self.conn is not None:
            self.conn.close()
        self.conn = new_conn
        self.db_path = path
        self.setWindowTitle("Excel 转 SQL — %s" % path)
        QSettings("excel-to-sql", "excel-to-sql").setValue(
            "last_db", str(Path(path).resolve()))
        self._reload_catalog()

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

    def _reload_catalog(self, checked=None):
        self.catalog.load(library.list_tree(self.conn), checked=checked)
        self.stack.setCurrentIndex(1)

    # ---------- 目录交互 ----------

    def _current_table(self):
        return self.catalog.table_of(self.catalog.currentItem())

    def _table_columns(self, table):
        if table not in self._columns_cache:
            self._columns_cache[table] = [
                name for name, _t in db_browser.table_columns(self.conn, table)]
        return self._columns_cache[table]

    def _on_item_changed(self, current, _previous):
        table = self.catalog.table_of(current)
        if not table or self.conn is None:
            return
        cols = self._table_columns(table)
        # 条件列下拉框列出该子表全部列名（中文原样）；跨表搜索时也可手动输入其他列名
        for entry in self.cond_rows:
            entry["col"].clear()
            entry["col"].addItems(cols)
        title = "%s·全部" % table
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == title:
                self.tabs.setCurrentIndex(i)
                return
        self.tabs.addTab(DataTableWidget(self.conn, table, cols), title)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _on_table_moved(self, table, group):
        """拖动子表到另一个大表：更新目录归属后重建树（保留勾选状态）。"""
        try:
            library.move_table(self.conn, table, group)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "移动失败", str(e))
            return
        checked = set(self.catalog.checked_tables())
        self._reload_catalog(checked=checked)
        self.statusBar().showMessage("已将「%s」移动到大表「%s」" % (table, group), 5000)

    def _on_group_renamed(self, old, new):
        """重命名大表：仅目录标签，子表归属与数据不变。"""
        try:
            library.rename_group(self.conn, old, new)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "重命名失败", str(e))
            return
        checked = set(self.catalog.checked_tables())
        self._reload_catalog(checked=checked)
        self.statusBar().showMessage("大表「%s」已重命名为「%s」" % (old, new), 5000)

    # ---------- 条件与搜索 ----------

    def _add_cond_row(self):
        cols = self._table_columns(self._current_table()) if self.conn else []
        row_widget = QWidget()
        col_combo = QComboBox()
        col_combo.setEditable(True)            # 跨表搜索时可输入其他子表的列名
        col_combo.setInsertPolicy(QComboBox.NoInsert)
        col_combo.addItems(cols)
        col_combo.setMinimumWidth(160)
        col_combo.setToolTip("列名（来自当前子表表头；跨表搜索可输入其他列名）")
        op_combo = QComboBox()
        for op, label in OPERATOR_LABELS.items():
            op_combo.addItem(label, op)
        op_combo.setCurrentIndex(op_combo.findData(OP_CONTAINS))  # 默认「包含」
        value_edit = QLineEdit()
        value_edit.setPlaceholderText("搜索值，支持中文；多个值用逗号分隔；局部匹配可用 * 和 ?")
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
        # 范围：勾选的子表（正向）或未勾选的子表（反向），可跨大表
        inverse = self.scope_inverse.isChecked()
        checked = set(self.catalog.checked_tables())
        scope = [t for t in library.all_tables(self.conn)
                 if (t in checked) != inverse]
        if not scope:
            QMessageBox.information(
                self, "提示",
                "查找范围为空：请先在目录中%s" %
                ("取消勾选部分子表再做反向查找" if inverse else "勾选要查找的子表"))
            return

        conditions = []
        for entry in self.cond_rows:
            column = entry["col"].currentText().strip()
            value = entry["value"].text().strip()
            if not column and not value:
                continue
            if not column or not value:
                QMessageBox.information(self, "提示", "请补全条件：列名和搜索值都要填")
                return
            conditions.append(Condition(column, entry["op"].currentData(), value))
        if not conditions:
            QMessageBox.information(self, "提示", "请至少填写一个搜索条件")
            return

        combine = "AND" if self.and_radio.isChecked() else "OR"

        # 跨表查找预检：范围内多张子表时要求表头结构（列名+类型）完全一致
        if len(scope) > 1:
            ok, ref, offenders = db_browser.check_same_structure(self.conn, scope)
            if not ok:
                ref_cols = "、".join(n for n, _t in db_browser.table_structure(
                    self.conn, ref)) or "（无列）"
                diff_lines = "\n".join(
                    "  · %s：%s" % (t, "、".join(n for n, _t in struct) or "（无列）")
                    for t, struct in offenders)
                QMessageBox.warning(
                    self, "不能跨表查找",
                    "所选范围的 %d 张子表表头结构不一致，不能一起查找。\n\n"
                    "参考结构（%s）：\n  %s\n\n结构不一致的子表：\n%s\n\n"
                    "请调整勾选范围，只保留结构相同的子表（单表查找不受影响）。"
                    % (len(scope), ref, ref_cols, diff_lines))
                return

        self.result_seq += 1
        seq = self.result_seq
        mark = chr(0x2460 + seq - 1) if seq <= 20 else str(seq)
        widget = ScopeResultWidget(self.conn, scope, conditions, combine,
                                   inverse=inverse)
        self.tabs.addTab(widget, "搜索结果%s·%d表" % (mark, len(scope)))
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _reset_search(self):
        for entry in self.cond_rows[1:]:
            entry["widget"].deleteLater()
        self.cond_rows = self.cond_rows[:1]
        if self.cond_rows:
            self.cond_rows[0]["value"].clear()
        self.and_radio.setChecked(True)
        self.scope_normal.setChecked(True)

    def closeEvent(self, event):
        if self.conn is not None:
            self.conn.close()
        super().closeEvent(event)
