"""目录树控件：大表（Excel 文件）分组 → 子表两级目录。

- 子表带勾选框：勾选集合即搜索范围（可跨大表）
- 大表勾选框三态：批量勾选/取消其下全部子表
- 拖动子表到另一大表 = 更换目录归属（通过 table_moved 信号交给上层落库）
- 提供全选/全不选/反选方法与右键菜单（勾选切换、仅勾选、移动到大表）
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QInputDialog, QMenu, QTreeWidget,
                               QTreeWidgetItem)


class CatalogTree(QTreeWidget):
    table_moved = Signal(str, str)  # (子表名, 新大表名)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["目录（大表 / 子表）"])
        self.setDragDropMode(QTreeWidget.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self._updating = False
        self.itemChanged.connect(self._on_item_changed)

    # ---------- 构建与勾选 ----------

    def load(self, tree, checked=None):
        """tree: [(大表名, [子表名...])]；checked: 勾选的子表名集合（默认全部勾选）。"""
        self._updating = True
        checked = set(checked) if checked is not None else None
        self.clear()
        for gname, tables in tree:
            group = QTreeWidgetItem([gname])
            group.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable
                           | Qt.ItemIsDropEnabled)
            for tname in tables:
                child = QTreeWidgetItem([tname])
                child.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable
                               | Qt.ItemIsUserCheckable
                               | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
                child.setCheckState(
                    0, Qt.Checked if (checked is None or tname in checked)
                    else Qt.Unchecked)
                group.addChild(child)
            self._sync_group_state(group)
            self.addTopLevelItem(group)
            group.setExpanded(True)
        self._updating = False

    def _sync_group_state(self, group):
        states = [group.child(i).checkState(0)
                  for i in range(group.childCount())]
        if not states:
            group.setCheckState(0, Qt.Unchecked)
        elif all(s == Qt.Checked for s in states):
            group.setCheckState(0, Qt.Checked)
        elif all(s == Qt.Unchecked for s in states):
            group.setCheckState(0, Qt.Unchecked)
        else:
            group.setCheckState(0, Qt.PartiallyChecked)

    def _on_item_changed(self, item, column):
        if self._updating or column != 0:
            return
        self._updating = True
        if item.parent() is None:
            # 大表勾选框：批量作用于全部子表（半选视为全选）
            target = Qt.Unchecked if item.checkState(0) == Qt.Unchecked else Qt.Checked
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, target)
        else:
            self._sync_group_state(item.parent())
        self._updating = False

    # ---------- 查询 ----------

    def checked_tables(self):
        out = []
        for i in range(self.topLevelItemCount()):
            group = self.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.checkState(0) == Qt.Checked:
                    out.append(child.text(0))
        return out

    @staticmethod
    def table_of(item):
        """item 是子表则返回其名，否则返回空串。"""
        if item is not None and item.parent() is not None:
            return item.text(0)
        return ""

    # ---------- 批量勾选 ----------

    def check_all(self):
        self._set_all(Qt.Checked)

    def uncheck_all(self):
        self._set_all(Qt.Unchecked)

    def invert_all(self):
        self._updating = True
        for i in range(self.topLevelItemCount()):
            group = self.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                child.setCheckState(
                    0, Qt.Unchecked if child.checkState(0) == Qt.Checked
                    else Qt.Checked)
            self._sync_group_state(group)
        self._updating = False

    def _set_all(self, state):
        self._updating = True
        for i in range(self.topLevelItemCount()):
            group = self.topLevelItem(i)
            for j in range(group.childCount()):
                group.child(j).setCheckState(0, state)
            self._sync_group_state(group)
        self._updating = False

    def _set_group(self, group, state):
        self._updating = True
        for j in range(group.childCount()):
            group.child(j).setCheckState(0, state)
        self._sync_group_state(group)
        self._updating = False

    def _only(self, table):
        """仅勾选一张子表，其余全部取消。"""
        self._updating = True
        for i in range(self.topLevelItemCount()):
            group = self.topLevelItem(i)
            for j in range(group.childCount()):
                child = group.child(j)
                child.setCheckState(
                    0, Qt.Checked if child.text(0) == table else Qt.Unchecked)
            self._sync_group_state(group)
        self._updating = False

    def _only_group(self, group):
        self._updating = True
        for i in range(self.topLevelItemCount()):
            g = self.topLevelItem(i)
            state = Qt.Checked if g is group else Qt.Unchecked
            for j in range(g.childCount()):
                g.child(j).setCheckState(0, state)
            self._sync_group_state(g)
        self._updating = False

    # ---------- 右键菜单 ----------

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item is None:
            return
        menu = QMenu(self)
        if item.parent() is None:
            group = item
            menu.addAction("勾选本组全部子表",
                           lambda: self._set_group(group, Qt.Checked))
            menu.addAction("取消勾选本组",
                           lambda: self._set_group(group, Qt.Unchecked))
            menu.addAction("仅勾选本组（其余全不选）",
                           lambda: self._only_group(group))
        else:
            table = item.text(0)
            if item.checkState(0) == Qt.Checked:
                menu.addAction("取消勾选此表",
                               lambda: item.setCheckState(0, Qt.Unchecked))
            else:
                menu.addAction("勾选此表",
                               lambda: item.setCheckState(0, Qt.Checked))
            menu.addAction("仅勾选此表（其余全不选）",
                           lambda: self._only(table))
            menu.addSeparator()
            move = menu.addMenu("移动到大表…")
            for i in range(self.topLevelItemCount()):
                group = self.topLevelItem(i)
                if group is item.parent():
                    continue
                gname = group.text(0)
                move.addAction(gname, lambda n=gname: self.table_moved.emit(table, n))
            move.addAction("新建大表…", lambda: self._move_to_new_group(table))
        menu.exec(event.globalPos())

    def _move_to_new_group(self, table):
        name, ok = QInputDialog.getText(self, "新建大表", "大表名称：")
        if ok and name.strip():
            self.table_moved.emit(table, name.strip())

    # ---------- 拖动换组 ----------

    def dropEvent(self, event):
        source = self.currentItem()
        target = self.itemAt(event.pos())
        # 只允许拖动子表；目标必须是大表或某大表下的子表
        if source is None or source.parent() is None or target is None:
            event.ignore()
            return
        group_item = target if target.parent() is None else target.parent()
        if group_item is source.parent():
            event.ignore()  # 同一大表内，无需移动
            return
        event.setDropAction(Qt.MoveAction)
        event.accept()
        self.table_moved.emit(source.text(0), group_item.text(0))
