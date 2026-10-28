"""Commit history with graph, search and commit details."""
from __future__ import annotations

import html
import time

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer, QUrl
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QPushButton, QSplitter,
                               QTableView, QTextBrowser, QVBoxLayout, QWidget)

from . import icons, theme
from .diffview import DiffView
from .graph import CommitModel, GraphDelegate, layout, parse_refs
from .i18n import T

PAGE = 2000


class HistoryPanel(QWidget):
    def __init__(self, rw, parent=None):
        super().__init__(parent)
        self.rw = rw
        self.limit = PAGE
        self.scope = "all"
        self._dirty = True
        self._sig = None
        self._cur_sha = None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        self.cb_scope = QComboBox()
        self.cb_scope.addItem(T("所有分支", "All branches"), "all")
        self.cb_scope.addItem(T("目前分支", "Current branch"), "current")
        self.cb_scope.currentIndexChanged.connect(self._scope_changed)
        self.cb_field = QComboBox()
        for val, txt in (("message", T("訊息", "Message")), ("author", T("作者", "Author")),
                         ("content", T("內容 (-S)", "Content (-S)")), ("regex", T("內容 (-G 正規)", "Content (-G regex)")),
                         ("path", T("檔案路徑", "File path")), ("sha", "SHA / ref"),
                         ("since", T("起始日期", "Since date"))):
            self.cb_field.addItem(txt, val)
        self.search = QLineEdit()
        self.search.setPlaceholderText(T("搜尋提交…  (Enter)", "Search commits…  (Enter)"))
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self.reload)
        self.search.textChanged.connect(lambda t: (not t) and self.reload())
        self.btn_first_parent = QPushButton(T("僅第一父提交", "First parent"))
        self.btn_first_parent.setCheckable(True)
        self.btn_first_parent.setProperty("flat", True)
        self.btn_first_parent.toggled.connect(lambda *_: self.reload())
        self.btn_nomerges = QPushButton(T("隱藏合併", "No merges"))
        self.btn_nomerges.setCheckable(True)
        self.btn_nomerges.setProperty("flat", True)
        self.btn_nomerges.toggled.connect(lambda *_: self.reload())
        bar.addWidget(self.cb_scope)
        bar.addWidget(self.cb_field)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.btn_first_parent)
        bar.addWidget(self.btn_nomerges)
        v.addLayout(bar)

        split = QSplitter(Qt.Vertical)
        v.addWidget(split, 1)
        self.model = CommitModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(0, GraphDelegate(self.table))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 80)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.selectionModel().selectionChanged.connect(self._sel_changed)
        self.table.doubleClicked.connect(self._dbl)
        self.table.verticalScrollBar().valueChanged.connect(self._maybe_more)
        split.addWidget(self.table)

        bottom = QSplitter(Qt.Horizontal)
        left = QSplitter(Qt.Vertical)
        self.info = QTextBrowser()
        self.info.setOpenLinks(False)
        self.info.anchorClicked.connect(self._anchor)
        self.files = QListWidget()
        self.files.currentItemChanged.connect(self._file_changed)
        self.files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._file_menu)
        left.addWidget(self.info)
        left.addWidget(self.files)
        left.setSizes([220, 200])
        self.diff = DiffView(self)
        self.diff.optionsChanged.connect(lambda: self._file_changed(self.files.currentItem(), None))
        bottom.addWidget(left)
        bottom.addWidget(self.diff)
        bottom.setSizes([380, 800])
        split.addWidget(bottom)
        split.setSizes([450, 380])

    # ------------------------------------------------------------------ loading
    def mark_dirty(self):
        self._dirty = True
        if self.isVisible():
            self.reload()

    def showEvent(self, e):
        super().showEvent(e)
        if self._dirty:
            QTimer.singleShot(0, self.reload)

    def _scope_changed(self):
        self.scope = self.cb_scope.currentData()
        self.reload()

    def set_scope_ref(self, ref):
        i = self.cb_scope.findData(ref)
        if i < 0:
            self.cb_scope.addItem(ref, ref)
            i = self.cb_scope.count() - 1
        self.cb_scope.setCurrentIndex(i)

    def _search_args(self):
        q = self.search.text().strip()
        if not q:
            return [], None
        f = self.cb_field.currentData()
        if f == "message":
            return ["-i", f"--grep={q}"], None
        if f == "author":
            return ["-i", f"--author={q}"], None
        if f == "content":
            return [f"-S{q}"], None
        if f == "regex":
            return [f"-G{q}"], None
        if f == "path":
            return [], [q]
        if f == "since":
            return [f"--since={q}"], None
        return [], None

    def reload(self):
        repo = self.rw.repo
        self._dirty = False
        extra, paths = self._search_args()
        if self.btn_first_parent.isChecked():
            extra.append("--first-parent")
        if self.btn_nomerges.isChecked():
            extra.append("--no-merges")
        scope = self.scope
        q = self.search.text().strip()
        if self.cb_field.currentData() == "sha" and q:
            scope = q
        commits = repo.log(scope=scope, limit=self.limit, extra=extra, paths=paths) if repo.head_valid() or scope == "all" else []
        head = repo.git("rev-parse", "HEAD", check=False).strip()
        sig = (tuple(c.sha + c.refs for c in commits[:200]), len(commits), head)
        if sig == self._sig:
            return
        self._sig = sig
        rows = layout(commits)
        branch = repo.current_branch()
        for r in rows:
            r.refs = parse_refs(r.commit.refs, branch)
        keep = self._cur_sha
        vpos = self.table.verticalScrollBar().value()
        self.model.set_rows(rows, head)
        self.table.verticalScrollBar().setValue(vpos)
        if keep:
            self.select_sha(keep, scroll=False)
        if not rows:
            self.info.setHtml(f"<p style='color:{theme.C['muted']}'>" +
                              T("還沒有任何提交。", "No commits yet.") + "</p>")
            self.files.clear()
            self.diff.clear()

    def _maybe_more(self, v):
        sb = self.table.verticalScrollBar()
        if v >= sb.maximum() - 5 and len(self.model.rows) >= self.limit:
            self.limit += PAGE
            self._sig = None
            self.reload()

    def select_sha(self, sha, scroll=True):
        for i, r in enumerate(self.model.rows):
            if r.commit.sha.startswith(sha):
                idx = self.model.index(i, 0)
                self.table.selectionModel().select(idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
                self.table.setCurrentIndex(idx)
                if scroll:
                    self.table.scrollTo(idx, QAbstractItemView.PositionAtCenter)
                return True
        return False

    def jump_to(self, ref):
        sha = self.rw.repo.git("rev-parse", ref + "^{commit}", check=False).strip()
        if not sha:
            return
        if not self.select_sha(sha):
            # not loaded yet: load more until found (bounded)
            for _ in range(10):
                self.limit += PAGE
                self._sig = None
                self.reload()
                if self.select_sha(sha):
                    break

    # ------------------------------------------------------------------ selection
    def selected_commits(self):
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.model.rows[r].commit for r in rows]

    def _sel_changed(self, *_):
        cs = self.selected_commits()
        if not cs:
            return
        if len(cs) == 2:
            self._show_compare(cs[1], cs[0])
            return
        c = cs[0]
        if c.sha == self._cur_sha and self.files.count():
            return
        self._cur_sha = c.sha
        self._compare = None
        self._show_commit(c.sha)

    def _show_commit(self, sha):
        repo = self.rw.repo
        d = repo.commit_details(sha)
        if not d:
            return
        C = theme.C
        e = html.escape
        subject, _, body = d["message"].partition("\n")
        sig = {"G": T("✔ 有效簽章", "✔ Good signature"), "B": T("✘ 簽章錯誤", "✘ Bad signature"),
               "U": T("? 簽章有效但未受信任", "? Good, untrusted"), "X": T("簽章已過期", "Expired signature"),
               "Y": T("金鑰已過期", "Expired key"), "R": T("金鑰已撤銷", "Revoked key"),
               "E": T("無法驗證簽章", "Cannot verify")}.get(d["sig"], "")
        parents = " ".join(f"<a href='sha:{p}'>{p[:8]}</a>" for p in d["parents"]) or "—"
        rows = [
            ("SHA", f"<code>{d['sha']}</code>"),
            (T("父提交", "Parents"), parents),
            (T("作者", "Author"), f"{e(d['author'])} &lt;{e(d['email'])}&gt; · {d['adate'][:19].replace('T', ' ')}"),
        ]
        if d["committer"] != d["author"] or d["cdate"] != d["adate"]:
            rows.append((T("提交者", "Committer"), f"{e(d['committer'])} &lt;{e(d['cemail'])}&gt; · {d['cdate'][:19].replace('T', ' ')}"))
        if d["refs"]:
            rows.append((T("參照", "Refs"), e(d["refs"])))
        if sig:
            rows.append((T("簽章", "Signature"), e(sig + (" — " + d["signer"] if d["signer"] else ""))))
        if d["notes"]:
            rows.append((T("備註", "Notes"), e(d["notes"]).replace("\n", "<br>")))
        tbl = "".join(f"<tr><td style='color:{C['muted']};padding-right:10px;white-space:nowrap'>{k}</td><td>{v}</td></tr>"
                      for k, v in rows)
        self.info.setHtml(
            f"<div style='font-size:11pt;font-weight:600;margin-bottom:6px'>{e(subject)}</div>"
            f"<table cellspacing=0 cellpadding=2>{tbl}</table>"
            + (f"<pre style='white-space:pre-wrap;font-family:inherit;margin-top:8px'>{e(body.strip())}</pre>" if body.strip() else ""))
        self._fill_files(repo.changed_files(sha), sha, None)

    def _show_compare(self, a, b):
        """Two commits selected: show diff between them."""
        self._cur_sha = None
        self._compare = (a.sha, b.sha)
        e = html.escape
        self.info.setHtml(
            f"<div style='font-weight:600'>{T('比較兩個提交', 'Comparing two commits')}</div>"
            f"<p><code>{a.sha[:8]}</code> {e(a.subject)}<br>→ <code>{b.sha[:8]}</code> {e(b.subject)}</p>")
        self._fill_files(self.rw.repo.changed_files(b.sha, parent=a.sha), b.sha, a.sha)

    def _fill_files(self, files, sha, parent):
        self.files.blockSignals(True)
        self.files.clear()
        allit = QListWidgetItem(icons.icon("list"), T(f"全部檔案 ({len(files)})", f"All files ({len(files)})"))
        allit.setData(Qt.UserRole, (sha, None, parent))
        self.files.addItem(allit)
        from .changes import STATUS_COLOR
        from PySide6.QtGui import QBrush, QColor
        for st, path, orig in files:
            it = QListWidgetItem(f"{st}   {path}" + (f"   ← {orig}" if orig else ""))
            it.setData(Qt.UserRole, (sha, path, parent))
            it.setForeground(QBrush(QColor(STATUS_COLOR.get(st, theme.C["text"]))))
            self.files.addItem(it)
        self.files.blockSignals(False)
        self.files.setCurrentRow(1 if len(files) == 1 else 0)

    def _file_changed(self, it, _prev):
        if not it:
            return
        sha, path, parent = it.data(Qt.UserRole)
        txt = self.rw.repo.diff_commit(sha, path, self.diff.diff_opts(), parent=parent)
        self.diff.set_diff(txt, "readonly", path or sha[:10])

    def _anchor(self, url: QUrl):
        s = url.toString()
        if s.startswith("sha:"):
            self.jump_to(s[4:])

    def _dbl(self, idx):
        c = self.model.rows[idx.row()].commit
        from . import actions
        actions.checkout_commit(self.rw, c.sha)

    # ------------------------------------------------------------------ menus
    def _menu(self, pos):
        m = self.build_menu()
        if m:
            m.exec(self.table.viewport().mapToGlobal(pos))

    def build_menu(self):
        cs = self.selected_commits()
        if not cs:
            return None
        from . import actions
        rw = self.rw
        m = QMenu(self)
        c = cs[0]
        if len(cs) == 1:
            r = self.model.rows[self.table.currentIndex().row()] if self.table.currentIndex().isValid() else None
            refs = r.refs if r and r.commit.sha == c.sha else []
            branches = [n for k, n in refs if k in ("branch", "head")]
            remotes = [n for k, n in refs if k == "remote"]
            if branches or remotes:
                co = m.addMenu(icons.icon("branch"), T("簽出分支", "Checkout branch"))
                for b in branches:
                    co.addAction(b, lambda b=b: actions.checkout(rw, b))
                for b in remotes:
                    co.addAction(b, lambda b=b: actions.checkout_remote(rw, b))
            m.addAction(T("簽出此提交（分離 HEAD）", "Checkout this commit (detached)"),
                        lambda: actions.checkout_commit(rw, c.sha))
            m.addAction(icons.icon("branch"), T("在此建立分支…", "Create branch here…"),
                        lambda: actions.new_branch(rw, c.sha))
            m.addAction(icons.icon("tag"), T("在此建立標籤…", "Create tag here…"),
                        lambda: actions.new_tag(rw, c.sha))
            m.addSeparator()
            m.addAction(icons.icon("cherry"), T("揀選 (cherry-pick)…", "Cherry-pick…"),
                        lambda: actions.cherry_pick(rw, [c.sha]))
            m.addAction(icons.icon("undo"), T("還原此提交 (revert)…", "Revert commit…"),
                        lambda: actions.revert(rw, [c.sha]))
            m.addAction(T("將目前分支重設到此…", "Reset current branch to here…"),
                        lambda: actions.reset(rw, c.sha))
            m.addAction(icons.icon("merge"), T("合併到目前分支…", "Merge into current branch…"),
                        lambda: actions.merge(rw, c.sha))
            m.addAction(icons.icon("rebase"), T("將目前分支變基到此…", "Rebase current branch onto here…"),
                        lambda: actions.rebase(rw, c.sha))
            m.addAction(T("從此處互動式變基…", "Interactive rebase from here…"),
                        lambda: actions.interactive_rebase(rw, c.sha))
            m.addAction(T("修正 (fixup) 到此提交", "Create fixup! commit for this"),
                        lambda: actions.fixup_commit(rw, c.sha))
            m.addSeparator()
            bis = m.addMenu(icons.icon("bug"), T("二分搜尋 (bisect)", "Bisect"))
            bis.addAction(T("標記為好 (good)", "Mark good"), lambda: actions.bisect(rw, "good", c.sha))
            bis.addAction(T("標記為壞 (bad)", "Mark bad"), lambda: actions.bisect(rw, "bad", c.sha))
            bis.addAction(T("略過 (skip)", "Skip"), lambda: actions.bisect(rw, "skip", c.sha))
            m.addAction(T("比較與工作區", "Compare with working tree"),
                        lambda: actions.compare_worktree(rw, c.sha))
            m.addAction(T("備註 (notes)…", "Notes…"), lambda: actions.edit_note(rw, c.sha))
            m.addAction(T("驗證簽章", "Verify signature"),
                        lambda: rw.run(["verify-commit", "-v", c.sha], "verify-commit", show_output=True))
            m.addAction(T("匯出封存檔 (archive)…", "Export archive…"), lambda: actions.archive(rw, c.sha))
        else:
            m.addAction(icons.icon("cherry"), T(f"揀選 {len(cs)} 個提交…", f"Cherry-pick {len(cs)} commits…"),
                        lambda: actions.cherry_pick(rw, [x.sha for x in reversed(cs)]))
            m.addAction(icons.icon("undo"), T(f"還原 {len(cs)} 個提交…", f"Revert {len(cs)} commits…"),
                        lambda: actions.revert(rw, [x.sha for x in cs]))
            if len(cs) == 2:
                m.addAction(T("比較這兩個提交", "Compare these two"),
                            lambda: self._show_compare(cs[1], cs[0]))
        m.addAction(T("產生修補檔 (format-patch)…", "Save as patch (format-patch)…"),
                    lambda: actions.format_patch(rw, [x.sha for x in cs]))
        m.addSeparator()
        m.addAction(T("複製 SHA", "Copy SHA"), lambda: rw.copy_text("\n".join(x.sha for x in cs)))
        m.addAction(T("複製簡短 SHA", "Copy short SHA"), lambda: rw.copy_text("\n".join(x.sha[:8] for x in cs)))
        m.addAction(T("複製訊息", "Copy message"), lambda: rw.copy_text("\n".join(x.subject for x in cs)))
        return m

    def _file_menu(self, pos):
        it = self.files.itemAt(pos)
        if not it:
            return
        sha, path, _parent = it.data(Qt.UserRole)
        if not path:
            return
        from . import actions
        rw = self.rw
        m = QMenu(self)
        m.addAction(T("檔案歷史", "File history"), lambda: rw.open_file_history(path))
        m.addAction(T("逐行追溯 (blame) 於此版本", "Blame at this revision"), lambda: rw.open_blame(path, sha))
        m.addAction(T("將工作區檔案還原成此版本", "Restore file to this revision"),
                    lambda: actions.restore_file_from(rw, path, sha))
        m.addAction(T("將工作區檔案還原成此版本之前", "Restore file to parent revision"),
                    lambda: actions.restore_file_from(rw, path, sha + "^"))
        m.addAction(T("另存此版本檔案…", "Save this revision as…"), lambda: actions.save_revision(rw, path, sha))
        m.addAction(T("複製路徑", "Copy path"), lambda: rw.copy_text(path))
        m.exec(self.files.viewport().mapToGlobal(pos))
