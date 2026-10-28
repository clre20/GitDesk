"""Model-based list that stays fast with tens of thousands of rows
(QListWidget creates one object per row and becomes slow at that size)."""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from PySide6.QtCore import (QAbstractListModel, QItemSelection, QItemSelectionModel, QModelIndex,
                            Qt, Signal)
from PySide6.QtGui import QBrush, QColor, QIcon
from PySide6.QtWidgets import QAbstractItemView, QListView

Row = Tuple[str, Optional[str], Any, str]   # text, color, data, tooltip


class RowsModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: List[Row] = []
        self.icons = {}
        self._brushes = {}

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, idx, role=Qt.DisplayRole):
        if not idx.isValid() or idx.row() >= len(self.rows):
            return None
        text, color, data, tip = self.rows[idx.row()]
        if role == Qt.DisplayRole:
            return text
        if role == Qt.ForegroundRole and color:
            b = self._brushes.get(color)
            if b is None:
                b = self._brushes[color] = QBrush(QColor(color))
            return b
        if role == Qt.ToolTipRole:
            return tip or None
        if role == Qt.DecorationRole:
            return self.icons.get(idx.row())
        if role == Qt.UserRole:
            return data
        return None


class FastList(QListView):
    selectionChangedSimple = Signal()
    activatedRow = Signal(object)          # data of double-clicked row
    currentDataChanged = Signal(object)    # data of the new current row

    def __init__(self, parent=None, multi=True, key=None):
        super().__init__(parent)
        self.key = key or (lambda d: d)
        self.model_ = RowsModel(self)
        self.setModel(self.model_)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection if multi else QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.selectionModel().selectionChanged.connect(lambda *_: self.selectionChangedSimple.emit())
        self.selectionModel().currentChanged.connect(self._cur)
        self.doubleClicked.connect(lambda idx: self.activatedRow.emit(idx.data(Qt.UserRole)))

    def _cur(self, cur, _prev):
        if cur.isValid():
            self.currentDataChanged.emit(cur.data(Qt.UserRole))

    # ------------------------------------------------------------------ data
    def set_rows(self, rows, keep_selection=True, icons=None):
        sm = self.selectionModel()
        keep, cur = set(), None
        if keep_selection:
            keep = {self.key(i.data(Qt.UserRole)) for i in sm.selectedRows()}
            ci = sm.currentIndex()
            cur = self.key(ci.data(Qt.UserRole)) if ci.isValid() else None
        vpos = self.verticalScrollBar().value()
        self.blockSignals(True)
        sm.blockSignals(True)
        self.model_.icons = icons or {}
        self.model_.set_rows(rows)
        if keep or cur is not None:
            sel = QItemSelection()
            cur_idx = None
            for r, row in enumerate(rows):
                k = self.key(row[2])
                if k in keep:
                    idx = self.model_.index(r)
                    sel.select(idx, idx)
                if cur is not None and k == cur:
                    cur_idx = self.model_.index(r)
            if not sel.isEmpty():
                sm.select(sel, QItemSelectionModel.Select)
            if cur_idx is not None:
                sm.setCurrentIndex(cur_idx, QItemSelectionModel.NoUpdate)
        sm.blockSignals(False)
        self.blockSignals(False)
        self.verticalScrollBar().setValue(vpos)

    def count(self):
        return len(self.model_.rows)

    def selected_data(self):
        rows = sorted(i.row() for i in self.selectionModel().selectedRows())
        return [self.model_.rows[r][2] for r in rows]

    def current_data(self):
        ci = self.selectionModel().currentIndex()
        return ci.data(Qt.UserRole) if ci.isValid() else None

    def current_is_selected(self):
        ci = self.selectionModel().currentIndex()
        return ci.isValid() and self.selectionModel().isSelected(ci)

    def data_at(self, pos):
        idx = self.indexAt(pos)
        return idx.data(Qt.UserRole) if idx.isValid() else None

    def select_row(self, r):
        if 0 <= r < self.count():
            idx = self.model_.index(r)
            self.selectionModel().setCurrentIndex(idx, QItemSelectionModel.ClearAndSelect)

    def clear_selection_quiet(self):
        sm = self.selectionModel()
        sm.blockSignals(True)
        sm.clearSelection()
        sm.blockSignals(False)
