"""导入向导（三步）：选择文件/Sheet → 配置表与列 → 执行导入。

导入在 QThread 中执行（独立连接），进度与日志通过信号回传 UI。
"""
import sqlite3
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWizard, QWizardPage)

from app.core.excel_reader import list_sheets, read_sample, iter_sheet_rows
from app.core.schema_builder import build_table_meta
from app.core.sqlite_writer import write_table
from app.models.column_meta import COLUMN_TYPES
from app.models.table_meta import REPLACE, RENAME, APPEND


class FilePage(QWizardPage):
    """步骤 1：选择文件（可多个），勾选要导入的 Sheet。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("步骤 1 / 3 — 选择文件与 Sheet")
        self.setSubTitle("支持 xlsx / csv；可一次选择多个文件，勾选要导入的 Sheet（空表默认不勾选）")
        self.sheet_list = QListWidget()
        add_btn = QPushButton("选择文件…")
        add_btn.clicked.connect(self._add_files)
        remove_btn = QPushButton("移除所选")
        remove_btn.clicked.connect(self._remove_selected)
        top = QHBoxLayout()
        top.addWidget(add_btn)
        top.addWidget(remove_btn)
        top.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.sheet_list)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择 Excel/CSV 文件", "",
            "Excel/CSV (*.xlsx *.xlsm *.csv *.tsv)")
        for f in files:
            try:
                sheets = list_sheets(f)
            except Exception as e:  # noqa: BLE001 - 读取失败逐文件提示，不中断
                QMessageBox.warning(self, "无法读取文件", "%s\n%s" % (f, e))
                continue
            for name, est in sheets:
                rows = "行数未知" if est is None else "约 %d 行" % max(est - 1, 0)
                item = QListWidgetItem("%s  ›  %s（%s）" % (f, name, rows))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if est is None or est > 1
                                   else Qt.Unchecked)
                item.setData(Qt.UserRole, (f, name))
                self.sheet_list.addItem(item)
        self.completeChanged.emit()

    def _remove_selected(self):
        for item in list(self.sheet_list.selectedItems()):
            self.sheet_list.takeItem(self.sheet_list.row(item))
        self.completeChanged.emit()

    def checked(self):
        return [self.sheet_list.item(i).data(Qt.UserRole)
                for i in range(self.sheet_list.count())
                if self.sheet_list.item(i).checkState() == Qt.Checked]

    def isComplete(self):
        return bool(self.checked())


class _SampleLoader(QThread):
    """后台读取各 Sheet 的数据样本并构建 TableMeta（避免卡 GUI 线程）。"""

    loaded = Signal(list)   # [(file, sheet, TableMeta)]
    failed = Signal(str)

    def __init__(self, entries, header_row, parent=None):
        super().__init__(parent)
        self.entries = entries      # [(file, sheet)]
        self.header_row = header_row

    def run(self):
        try:
            results = []
            used = set()
            for f, sheet in self.entries:
                header, sample = read_sample(f, sheet, header_row=self.header_row)
                meta = build_table_meta(sheet, header if self.header_row else None,
                                        sample, header_row=self.header_row,
                                        used_names=used)
                if meta is not None:
                    results.append((f, sheet, meta))
        except Exception as e:  # noqa: BLE001 - 失败原因回传 UI
            self.failed.emit(str(e))
            return
        self.loaded.emit(results)


class ConfigPage(QWizardPage):
    """步骤 2：逐 Sheet 确认表名、列配置（列名/类型/是否导入）并预览。

    样本读取在 _SampleLoader 后台线程进行，读取期间禁用下一步。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("步骤 2 / 3 — 配置表与列")
        self.setSubTitle("类型为自动推断结果，可修改；勾选要导入的列")
        self.metas = {}      # (file, sheet) -> TableMeta
        self._loaded_key = None
        self._loading = False
        self._loader = None
        self._gen = 0        # 加载代号：仅接受最新一次的结果

        self.sheet_combo = QComboBox()
        self.sheet_combo.currentIndexChanged.connect(self._on_sheet_switched)
        self.table_edit = QLineEdit()
        self.header_check = QCheckBox("首行是表头")
        self.header_check.stateChanged.connect(self._on_header_toggled)

        self.load_progress = QProgressBar()
        self.load_progress.setRange(0, 0)   # 不确定进度（滚动条动画）
        self.load_progress.hide()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #b25000;")

        head = QHBoxLayout()
        head.addWidget(QLabel("Sheet："))
        head.addWidget(self.sheet_combo, 1)
        head.addWidget(QLabel("表名："))
        head.addWidget(self.table_edit, 1)
        head.addWidget(self.header_check)

        self.column_table = QTableWidget()
        self.column_table.setColumnCount(4)
        self.column_table.setHorizontalHeaderLabels(["导入", "列名", "类型", "示例值"])
        self.column_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)

        self.preview = QTableWidget()
        self.preview.setEditTriggers(QTableWidget.NoEditTriggers)

        col_group = QGroupBox("列配置")
        col_layout = QVBoxLayout(col_group)
        col_layout.addWidget(self.column_table)
        preview_group = QGroupBox("数据预览（前 100 行）")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.addWidget(self.preview)

        layout = QVBoxLayout(self)
        layout.addLayout(head)
        layout.addWidget(self.load_progress)
        layout.addWidget(self.status_label)
        layout.addWidget(col_group, 2)
        layout.addWidget(preview_group, 3)

    # --- 后台加载 ---

    def _entries(self):
        return [self.sheet_combo.itemData(i) for i in range(self.sheet_combo.count())]

    def initializePage(self):
        entries = self.wizard().page(0).checked()
        self._start_loader(entries, header_row=True)

    def _start_loader(self, entries, header_row):
        self._gen += 1
        gen = self._gen
        self._loading = True
        self.header_check.blockSignals(True)
        self.header_check.setChecked(header_row)
        self.header_check.blockSignals(False)
        self.metas = {}
        self._loaded_key = None
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        self.sheet_combo.blockSignals(False)
        self.table_edit.clear()
        self.column_table.setRowCount(0)
        self.preview.setRowCount(0)
        self.preview.setColumnCount(0)
        self.load_progress.show()
        self.status_label.setText("正在读取数据样本（后台线程，不阻塞界面）…")
        self.completeChanged.emit()

        loader = _SampleLoader(entries, header_row)
        loader.loaded.connect(lambda res, g=gen: self._on_loaded(g, res))
        loader.failed.connect(lambda msg, g=gen: self._on_load_failed(g, msg))
        self._loader = loader  # 保引用防止线程被回收
        loader.start()

    def _on_loaded(self, gen, results):
        if gen != self._gen:
            return  # 过期结果（用户已返回重进）
        self._loading = False
        self.metas = {}
        self.sheet_combo.blockSignals(True)
        self.sheet_combo.clear()
        for f, sheet, meta in results:
            self.metas[(f, sheet)] = meta
            self.sheet_combo.addItem(sheet, (f, sheet))
        self.sheet_combo.blockSignals(False)
        self.load_progress.hide()
        self.status_label.setText("")
        if self.sheet_combo.count():
            self._load_meta()
        self.completeChanged.emit()

    def _on_load_failed(self, gen, message):
        if gen != self._gen:
            return
        self._loading = False
        self.load_progress.hide()
        self.status_label.setText("读取失败：%s" % message)
        self.completeChanged.emit()

    def _on_header_toggled(self):
        if self._loading or self.sheet_combo.count() == 0:
            return
        self._start_loader(self._entries(),
                           header_row=self.header_check.isChecked())

    def _on_sheet_switched(self, _index):
        if not self._loading and self.sheet_combo.count():
            self._save_current()
            self._load_meta()

    def _current_key(self):
        return self.sheet_combo.currentData()

    def _save_current(self):
        """把当前界面编辑写回已加载的 TableMeta（供向导第 3 步使用）。"""
        meta = self.metas.get(self._loaded_key)
        if meta is None:
            return
        name = self.table_edit.text().strip()
        if name:
            meta.name = name
        for r, col in enumerate(meta.columns):
            check = self.column_table.item(r, 0)
            if check is not None:
                col.include = check.checkState() == Qt.Checked
            name_item = self.column_table.item(r, 1)
            if name_item is not None and name_item.text().strip():
                col.name = name_item.text().strip()
            combo = self.column_table.cellWidget(r, 2)
            if combo is not None:
                col.col_type = combo.currentData()

    def _load_meta(self):
        key = self._current_key()
        meta = self.metas.get(key)
        if meta is None:
            return
        self._loading = True
        self._loaded_key = key
        self.table_edit.setText(meta.name)
        self.header_check.setChecked(meta.header_row)

        self.column_table.setRowCount(len(meta.columns))
        for r, col in enumerate(meta.columns):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked if col.include else Qt.Unchecked)
            self.column_table.setItem(r, 0, check)
            self.column_table.setItem(r, 1, QTableWidgetItem(col.name))
            type_combo = QComboBox()
            for t in COLUMN_TYPES:
                type_combo.addItem(t, t)
            type_combo.setCurrentIndex(COLUMN_TYPES.index(col.col_type))
            self.column_table.setCellWidget(r, 2, type_combo)
            self.column_table.setItem(r, 3, QTableWidgetItem(col.example))

        f, sheet = key
        _header, sample = read_sample(f, sheet, header_row=meta.header_row,
                                      limit=100)
        names = [c.name if c.include else "（跳过）%s" % c.name
                 for c in meta.columns]
        self.preview.setColumnCount(len(meta.columns))
        self.preview.setRowCount(min(len(sample), 100))
        self.preview.setHorizontalHeaderLabels(names)
        for r, row in enumerate(sample[:100]):
            for c, col in enumerate(meta.columns):
                v = row[col.index] if col.index < len(row) else None
                self.preview.setItem(r, c,
                                     QTableWidgetItem("" if v is None else str(v)))
        self._loading = False
        self.completeChanged.emit()

    def isComplete(self):
        if self._loading or not self.sheet_combo.count():
            return False
        meta = self.metas.get(self._current_key())
        return meta is not None and bool(meta.included_columns)


class ImportThread(QThread):
    log = Signal(str)
    step = Signal(int)                 # 总体进度 0-100
    table_done = Signal(str, int, float)
    ok = Signal(int, int)              # 表数、总行数
    fail = Signal(str)

    def __init__(self, db_path, entries, conflict, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.entries = entries         # [(file, sheet, TableMeta)]
        self.conflict = conflict

    def run(self):
        conn = sqlite3.connect(self.db_path)
        total_rows = 0
        try:
            from app.core.library import init_library, register_table
            init_library(conn)
            est_map = {}
            for f, _sheet, _meta in self.entries:
                if f not in est_map:
                    try:
                        est_map[f] = dict(list_sheets(f))
                    except Exception:  # noqa: BLE001 - 行数估计失败不阻断导入
                        est_map[f] = {}
            n = len(self.entries)
            for i, (f, sheet, meta) in enumerate(self.entries):
                meta.conflict = self.conflict
                self.log.emit("⟳ %s → 表 %s …" % (sheet, meta.name))
                est = est_map.get(f, {}).get(sheet)
                est_data = max((est or 2) - 1, 1)
                base = int(i * 100 / n)
                span = int(100 / n)

                def cb(done, _b=base, _s=span, _e=est_data):
                    self.step.emit(min(_b + int(_s * done / _e), 99))

                rows = iter_sheet_rows(f, sheet, header_row=meta.header_row)
                stats = write_table(conn, meta, rows, progress_cb=cb)
                # 目录登记：文件（去扩展名）= 大表分组，Sheet = 子表
                register_table(conn, Path(f).stem, stats.table)
                self.table_done.emit(stats.table, stats.rows_written,
                                     stats.elapsed)
                total_rows += stats.rows_written
            conn.commit()
            self.step.emit(100)
            self.ok.emit(n, total_rows)
        except Exception as e:  # noqa: BLE001 - 失败原因回传 UI 弹窗
            try:
                conn.rollback()
            except Exception:
                pass
            self.fail.emit(str(e))
        finally:
            conn.close()


class RunPage(QWizardPage):
    """步骤 3：选择输出库与冲突策略，执行导入。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("步骤 3 / 3 — 执行导入")
        self.setSubTitle("导入完成后回到主界面，表列表自动刷新")
        self._done = False
        self.thread = None

        self.db_edit = QLineEdit()
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        self.conflict_combo = QComboBox()
        self.conflict_combo.addItem("覆盖同名表（重建）", REPLACE)
        self.conflict_combo.addItem("重命名新表（保留旧表）", RENAME)
        self.conflict_combo.addItem("追加数据（要求结构一致）", APPEND)
        self.start_btn = QPushButton("开始导入")
        self.start_btn.clicked.connect(self._start)

        self.progress = QProgressBar()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.summary = QLabel("")

        out_bar = QHBoxLayout()
        out_bar.addWidget(QLabel("数据库："))
        out_bar.addWidget(self.db_edit, 1)
        out_bar.addWidget(browse)
        opt_bar = QHBoxLayout()
        opt_bar.addWidget(QLabel("同名表："))
        opt_bar.addWidget(self.conflict_combo)
        opt_bar.addStretch(1)
        opt_bar.addWidget(self.start_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(out_bar)
        layout.addLayout(opt_bar)
        layout.addWidget(self.progress)
        layout.addWidget(self.log, 1)
        layout.addWidget(self.summary)

    def initializePage(self):
        if not self.db_edit.text():
            docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            self.db_edit.setText(str(Path(docs) / "excel_to_sql.db"))
        self.progress.setValue(0)
        self.log.clear()
        self.summary.clear()
        self._set_running(False)
        self._done = False
        self.completeChanged.emit()

    def isComplete(self):
        return self._done

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(self, "选择输出数据库",
                                              self.db_edit.text(),
                                              "SQLite 数据库 (*.db)")
        if path:
            self.db_edit.setText(path)

    def _set_running(self, running):
        self.start_btn.setEnabled(not running)
        self.db_edit.setEnabled(not running)
        self.conflict_combo.setEnabled(not running)

    def _start(self):
        db_path = self.db_edit.text().strip()
        if not db_path:
            QMessageBox.warning(self, "提示", "请先选择输出数据库路径")
            return
        config = self.wizard().page(1)
        config._save_current()
        entries = [(f, sheet, meta) for (f, sheet), meta in config.metas.items()
                   if meta.included_columns]
        if not entries:
            QMessageBox.warning(self, "提示", "没有可导入的表")
            return

        self._set_running(True)
        self._done = False
        self.completeChanged.emit()
        self.log.appendPlainText("开始导入：%d 张表 → %s" % (len(entries), db_path))
        self.thread = ImportThread(db_path, entries,
                                   self.conflict_combo.currentData())
        self.thread.log.connect(self.log.appendPlainText)
        self.thread.step.connect(self.progress.setValue)
        self.thread.table_done.connect(
            lambda name, rows, secs: self.log.appendPlainText(
                "✅ %s：%d 行（%.2fs）" % (name, rows, secs)))
        self.thread.ok.connect(self._on_ok)
        self.thread.fail.connect(self._on_fail)
        self.thread.start()

    def _on_ok(self, tables, rows):
        self.summary.setText("导入完成：%d 张表 / %d 行 → %s"
                             % (tables, rows, self.db_edit.text()))
        self.log.appendPlainText("全部完成。")
        self._set_running(False)
        self._done = True
        self.completeChanged.emit()

    def _on_fail(self, message):
        self.log.appendPlainText("✗ 导入失败：%s" % message)
        QMessageBox.critical(self, "导入失败", message)
        self._set_running(False)


class ImportWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入 Excel")
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        self.addPage(FilePage())
        self.addPage(ConfigPage())
        self.addPage(RunPage())
        self.db_path = None

    def accept(self):
        run_page = self.page(2)
        if getattr(run_page, "_done", False):
            self.db_path = run_page.db_edit.text().strip()
        super().accept()
