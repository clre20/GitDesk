"""Generic form dialog used by most git operations."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QRadioButton, QSpinBox, QVBoxLayout,
                               QWidget, QCompleter)

from .i18n import T


class Form(QDialog):
    def __init__(self, parent, title: str, description: str = "", ok_text: str = None,
                 danger: bool = False, width: int = 520):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self._w = {}
        self._getters = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        h = QLabel(title)
        h.setProperty("h2", True)
        lay.addWidget(h)
        if description:
            d = QLabel(description)
            d.setWordWrap(True)
            d.setProperty("muted", True)
            d.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(d)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.form.setHorizontalSpacing(12)
        self.form.setVerticalSpacing(8)
        lay.addLayout(self.form)
        lay.addStretch(1)
        bb = QDialogButtonBox()
        self.ok = bb.addButton(ok_text or T("確定", "OK"), QDialogButtonBox.AcceptRole)
        self.ok.setProperty("accent", True)
        if danger:
            self.ok.setStyleSheet("QPushButton{background:#c42b1c;border-color:#c42b1c;color:white;}")
        bb.addButton(T("取消", "Cancel"), QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.validator = None

    # ------------------------------------------------------------------ fields
    def _row(self, label, w):
        self.form.addRow(label + ("" if not label else ""), w)

    def text(self, key, label, default="", placeholder="", password=False, completions=None):
        e = QLineEdit(default)
        e.setPlaceholderText(placeholder)
        if password:
            e.setEchoMode(QLineEdit.Password)
        if completions:
            c = QCompleter(completions, e)
            c.setCaseSensitivity(Qt.CaseInsensitive)
            c.setFilterMode(Qt.MatchContains)
            e.setCompleter(c)
        self._row(label, e)
        self._w[key] = e
        self._getters[key] = lambda: e.text().strip()
        return e

    def multiline(self, key, label, default="", placeholder="", height=110):
        e = QPlainTextEdit(default)
        e.setPlaceholderText(placeholder)
        e.setFixedHeight(height)
        self._row(label, e)
        self._w[key] = e
        self._getters[key] = lambda: e.toPlainText()
        return e

    def combo(self, key, label, items, current=None, editable=False):
        cb = QComboBox()
        cb.setEditable(editable)
        for it in items:
            if isinstance(it, tuple):
                cb.addItem(it[1], it[0])
            else:
                cb.addItem(it, it)
        if current is not None:
            i = cb.findData(current)
            if i >= 0:
                cb.setCurrentIndex(i)
            elif editable:
                cb.setEditText(current)
        if editable:
            cb.completer().setFilterMode(Qt.MatchContains)
            cb.completer().setCompletionMode(QCompleter.PopupCompletion)
        self._row(label, cb)
        self._w[key] = cb

        def get():
            if editable:
                t = cb.currentText().strip()
                i = cb.findText(t)
                return cb.itemData(i) if i >= 0 and cb.itemData(i) is not None else t
            return cb.currentData()
        self._getters[key] = get
        return cb

    def check(self, key, label, default=False, tooltip=""):
        c = QCheckBox(label)
        c.setChecked(default)
        if tooltip:
            c.setToolTip(tooltip)
        self.form.addRow("", c)
        self._w[key] = c
        self._getters[key] = c.isChecked
        return c

    def spin(self, key, label, value=0, lo=0, hi=1_000_000, special=None):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(value)
        if special:
            s.setSpecialValueText(special)
        self._row(label, s)
        self._w[key] = s
        self._getters[key] = s.value
        return s

    def radio(self, key, label, options, default=None):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        grp = QButtonGroup(box)
        btns = {}
        for val, txt in options:
            rb = QRadioButton(txt)
            grp.addButton(rb)
            v.addWidget(rb)
            btns[val] = rb
            if val == default:
                rb.setChecked(True)
        if default is None and options:
            btns[options[0][0]].setChecked(True)
        self._row(label, box)
        self._w[key] = btns

        def get():
            for val, rb in btns.items():
                if rb.isChecked():
                    return val
        self._getters[key] = get
        return btns

    def path(self, key, label, default="", directory=True, save=False, filter=""):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        e = QLineEdit(default)
        b = QPushButton(T("瀏覽…", "Browse…"))

        def pick():
            start = e.text() or os.path.expanduser("~")
            if directory:
                p = QFileDialog.getExistingDirectory(self, label, start)
            elif save:
                p, _ = QFileDialog.getSaveFileName(self, label, start, filter)
            else:
                p, _ = QFileDialog.getOpenFileName(self, label, start, filter)
            if p:
                e.setText(os.path.normpath(p))
        b.clicked.connect(pick)
        h.addWidget(e, 1)
        h.addWidget(b)
        self._row(label, box)
        self._w[key] = e
        self._getters[key] = lambda: e.text().strip()
        return e

    def label(self, text):
        l = QLabel(text)
        l.setWordWrap(True)
        l.setProperty("muted", True)
        self.form.addRow("", l)
        return l

    def widget(self, key):
        return self._w[key]

    # ------------------------------------------------------------------ results
    def values(self):
        return {k: g() for k, g in self._getters.items()}

    def _accept(self):
        if self.validator:
            err = self.validator(self.values())
            if err:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, self.windowTitle(), err)
                return
        self.accept()

    def ask(self):
        return self.values() if self.exec() == QDialog.Accepted else None
