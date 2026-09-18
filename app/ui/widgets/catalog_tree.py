"""目录树控件：大表（Excel 文件）分组 → 子表两级目录。

- 子表带勾选框：勾选集合即搜索范围（可跨大表）
- 大表勾选框三态：批量勾选/取消其下全部子表
- 拖动子表到另一大表 = 更换目录归属（通过 table_moved 信号交给上层落库）
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


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
