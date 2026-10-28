"""Left navigation tree: changes / history / branches / remotes / tags / stashes /
submodules / worktrees."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import icons, theme
from .i18n import T

ROLE_KIND = Qt.UserRole
ROLE_NAME = Qt.UserRole + 1
ROLE_DATA = Qt.UserRole + 2


class Sidebar(QWidget):
    navigate = Signal(str)                 # "changes" | "history"
    activated = Signal(str, str, object)   # kind, name, data (double click)
    selected = Signal(str, str, object)    # kind, name, data (single click)
    contextRequested = Signal(str, str, object, object)  # kind, name, data, global pos

    GROUPS = [
        ("local", "branch"), ("remote", "cloud"), ("tags", "tag"), ("stashes", "stash"),
        ("submodules", "box"), ("worktrees", "tree"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 0, 6)
        lay.setSpacing(6)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(T("篩選分支、標籤…", "Filter branches, tags…"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._ctx)
        self.tree.itemDoubleClicked.connect(self._dbl)
        self.tree.itemClicked.connect(self._click)
        self.tree.currentItemChanged.connect(lambda cur, _p: cur and self._click(cur))
        lay.addWidget(self.tree, 1)

        self.item_changes = self._top("changes", T("工作區變更", "Local Changes"), "changes")
        self.item_history = self._top("history", T("歷史記錄", "History"), "history")
        titles = {
            "local": T("本地分支", "Branches"), "remote": T("遠端", "Remotes"),
            "tags": T("標籤", "Tags"), "stashes": T("暫存堆疊 Stash", "Stashes"),
            "submodules": T("子模組", "Submodules"), "worktrees": T("工作樹", "Worktrees"),
        }
        self.groups = {}
        for key, ic in self.GROUPS:
            it = QTreeWidgetItem([titles[key]])
            it.setData(0, ROLE_KIND, "group:" + key)
            it.setIcon(0, icons.icon(ic))
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
            it.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(it)
            self.groups[key] = it
            it.setExpanded(key in ("local", "remote"))
        self._titles = titles

    def _top(self, kind, text, ic):
        it = QTreeWidgetItem([text])
        it.setData(0, ROLE_KIND, kind)
        it.setIcon(0, icons.icon(ic))
        self.tree.addTopLevelItem(it)
        return it

    # ------------------------------------------------------------------ populate
    def set_changes_count(self, n):
        self.item_changes.setText(0, T("工作區變更", "Local Changes") + (f"  ({n})" if n else ""))

    def select_nav(self, which):
        it = self.item_changes if which == "changes" else self.item_history
        self.tree.blockSignals(True)
        self.tree.setCurrentItem(it)
        self.tree.blockSignals(False)

    def populate(self, branches, remote_branches, remotes, tags, stashes, submodules, worktrees,
                 main_path):
        expanded = self._expanded_paths()
        cur_key = None
        ci = self.tree.currentItem()
        if ci:
            cur_key = (ci.data(0, ROLE_KIND), ci.data(0, ROLE_NAME))
        self.tree.setUpdatesEnabled(False)
        for g in self.groups.values():
            g.takeChildren()

        muted = QBrush(QColor(theme.C["muted"]))
        # local branches, grouped by folder (feature/x)
        for b in branches:
            parent = self._folder(self.groups["local"], b.name.split("/")[:-1], "local")
            label = b.name.split("/")[-1]
            it = QTreeWidgetItem([label])
            it.setData(0, ROLE_KIND, "branch")
            it.setData(0, ROLE_NAME, b.name)
            it.setData(0, ROLE_DATA, b)
            tip = b.name
            if b.upstream:
                tip += f"\n→ {b.upstream} {b.track}"
            tip += f"\n{b.sha[:8]} {b.subject}"
            it.setToolTip(0, tip)
            track = b.track.strip("[]")
            if track and track != "gone":
                a = track.replace("ahead ", "↑").replace("behind ", "↓").replace(",", "")
                it.setText(0, f"{label}   {a}")
            elif track == "gone":
                it.setText(0, f"{label}   ⚠")
            if b.current:
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
                it.setIcon(0, icons.accent("check"))
            else:
                it.setIcon(0, icons.icon("branch", theme.C["muted"]))
            parent.addChild(it)
        self.groups["local"].setText(0, f"{self._titles['local']}  ({len(branches)})")

        # remotes -> branches
        rnodes = {}
        for r in remotes:
            it = QTreeWidgetItem([r["name"]])
            it.setData(0, ROLE_KIND, "remote")
            it.setData(0, ROLE_NAME, r["name"])
            it.setData(0, ROLE_DATA, r)
            it.setIcon(0, icons.icon("globe"))
            it.setToolTip(0, f"fetch: {r['fetch']}\npush: {r['push']}")
            self.groups["remote"].addChild(it)
            rnodes[r["name"]] = it
        for b in remote_branches:
            rname, _, short = b.name.partition("/")
            node = rnodes.get(rname)
            if node is None:
                continue
            parent = self._folder(node, short.split("/")[:-1], "remote:" + rname)
            it = QTreeWidgetItem([short.split("/")[-1]])
            it.setData(0, ROLE_KIND, "remote_branch")
            it.setData(0, ROLE_NAME, b.name)
            it.setData(0, ROLE_DATA, b)
            it.setIcon(0, icons.icon("branch", theme.C["muted"]))
            it.setToolTip(0, b.name)
            parent.addChild(it)

        for t in tags:
            it = QTreeWidgetItem([t["name"]])
            it.setData(0, ROLE_KIND, "tag")
            it.setData(0, ROLE_NAME, t["name"])
            it.setData(0, ROLE_DATA, t)
            it.setIcon(0, icons.icon("tag", theme.C["muted"]))
            it.setToolTip(0, f"{t['name']} → {t['sha'][:8]}\n{t['subject']}")
            self.groups["tags"].addChild(it)
        self.groups["tags"].setText(0, f"{self._titles['tags']}  ({len(tags)})")

        for s in stashes:
            it = QTreeWidgetItem([f"{s.ref}  {s.message}"])
            it.setData(0, ROLE_KIND, "stash")
            it.setData(0, ROLE_NAME, s.ref)
            it.setData(0, ROLE_DATA, s)
            it.setIcon(0, icons.icon("stash", theme.C["muted"]))
            it.setToolTip(0, s.message)
            self.groups["stashes"].addChild(it)
        self.groups["stashes"].setText(0, f"{self._titles['stashes']}  ({len(stashes)})")

        for sm in submodules:
            state = {"-": T("未初始化", "not initialized"), "+": T("已變更", "modified"),
                     "U": T("衝突", "conflict")}.get(sm.state, "")
            it = QTreeWidgetItem([sm.path + (f"   ({state})" if state else "")])
            it.setData(0, ROLE_KIND, "submodule")
            it.setData(0, ROLE_NAME, sm.path)
            it.setData(0, ROLE_DATA, sm)
            it.setIcon(0, icons.icon("box", theme.C["muted"]))
            it.setToolTip(0, f"{sm.path}\n{sm.sha[:10]} {sm.describe}")
            self.groups["submodules"].addChild(it)
        self.groups["submodules"].setText(0, f"{self._titles['submodules']}  ({len(submodules)})")

        import os
        for w in worktrees:
            label = os.path.basename(w.path) or w.path
            extra = w.branch or (T("分離 HEAD", "detached") if w.detached else ("bare" if w.bare else ""))
            it = QTreeWidgetItem([f"{label}   [{extra}]" if extra else label])
            it.setData(0, ROLE_KIND, "worktree")
            it.setData(0, ROLE_NAME, w.path)
            it.setData(0, ROLE_DATA, w)
            it.setIcon(0, icons.icon("lock" if w.locked else "tree", theme.C["muted"]))
            it.setToolTip(0, w.path)
            if os.path.normcase(w.path) == os.path.normcase(main_path):
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
            self.groups["worktrees"].addChild(it)
        self.groups["worktrees"].setText(0, f"{self._titles['worktrees']}  ({len(worktrees)})")

        self._restore_expanded(expanded)
        self._apply_filter(self.filter.text())
        if cur_key and cur_key[0] not in ("changes", "history"):
            self._select_key(cur_key)
        self.tree.setUpdatesEnabled(True)

    def _folder(self, root, parts, ns):
        node = root
        for i, part in enumerate(parts):
            key = ns + ":" + "/".join(parts[:i + 1])
            found = None
            for k in range(node.childCount()):
                c = node.child(k)
                if c.data(0, ROLE_KIND) == "folder" and c.data(0, ROLE_NAME) == key:
                    found = c
                    break
            if not found:
                found = QTreeWidgetItem([part])
                found.setData(0, ROLE_KIND, "folder")
                found.setData(0, ROLE_NAME, key)
                found.setIcon(0, icons.icon("folder", theme.C["muted"]))
                node.addChild(found)
            node = found
        return node

    def _iter(self, item=None):
        if item is None:
            for i in range(self.tree.topLevelItemCount()):
                yield from self._iter(self.tree.topLevelItem(i))
            return
        yield item
        for i in range(item.childCount()):
            yield from self._iter(item.child(i))

    def _expanded_paths(self):
        return {(it.data(0, ROLE_KIND), it.data(0, ROLE_NAME)) for it in self._iter() if it.isExpanded()}

    def _restore_expanded(self, keys):
        for it in self._iter():
            k = (it.data(0, ROLE_KIND), it.data(0, ROLE_NAME))
            if k in keys:
                it.setExpanded(True)

    def _select_key(self, key):
        for it in self._iter():
            if (it.data(0, ROLE_KIND), it.data(0, ROLE_NAME)) == key:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(it)
                self.tree.blockSignals(False)
                return

    def _apply_filter(self, text):
        text = text.lower().strip()

        def visit(it):
            kind = it.data(0, ROLE_KIND) or ""
            if it.childCount() == 0:
                vis = not text or kind.startswith("group") or kind in ("changes", "history") \
                    or text in (it.data(0, ROLE_NAME) or it.text(0)).lower()
                it.setHidden(not vis)
                return vis
            any_vis = False
            for i in range(it.childCount()):
                any_vis |= visit(it.child(i))
            if kind.startswith("group"):
                it.setHidden(False)
                if text and any_vis:
                    it.setExpanded(True)
                return True
            it.setHidden(bool(text) and not any_vis and text not in it.text(0).lower())
            if text and any_vis:
                it.setExpanded(True)
            return any_vis

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))

    # ------------------------------------------------------------------ events
    def _info(self, it):
        return it.data(0, ROLE_KIND) or "", it.data(0, ROLE_NAME) or "", it.data(0, ROLE_DATA)

    def _click(self, it, _col=0):
        kind, name, data = self._info(it)
        if kind in ("changes", "history"):
            self.navigate.emit(kind)
        else:
            self.selected.emit(kind, name, data)

    def _dbl(self, it, _col):
        kind, name, data = self._info(it)
        if kind not in ("changes", "history", "folder") and not kind.startswith("group"):
            self.activated.emit(kind, name, data)

    def _ctx(self, pos):
        it = self.tree.itemAt(pos)
        if not it:
            return
        kind, name, data = self._info(it)
        self.contextRequested.emit(kind, name, data, self.tree.viewport().mapToGlobal(pos))
