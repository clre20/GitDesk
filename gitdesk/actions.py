"""All git operations exposed in the UI (dialogs + commands)."""
from __future__ import annotations

import os
import re

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMenu, QMessageBox

from . import icons
from .forms import Form
from .git import GitError
from .i18n import T


def _refs(rw, include_head=True):
    refs = rw.repo.all_refs_for_completion()
    return (["HEAD"] if include_head else []) + refs


def _remotes(rw):
    return [r["name"] for r in rw.repo.remotes()]


def _local_branches(rw):
    return [b.name for b in rw.repo.branches()]


def _dirty(rw):
    st = rw.changes.status
    return bool(st and (st.staged or [f for f in st.unstaged if f.kind != "?"]))


def _valid_ref_name(name):
    if not name:
        return T("請輸入名稱", "Please enter a name")
    try:
        from .git import run_git
        run_git(["check-ref-format", "--branch", name])
    except Exception:
        return T("名稱不合法", "Invalid name") + f": {name}"
    return None


# =========================================================================== checkout / branches
def checkout(rw, branch):
    rw.run(["switch", branch], T(f"簽出 {branch}", f"Checkout {branch}"))


def checkout_remote(rw, remote_branch):
    local = remote_branch.split("/", 1)[1] if "/" in remote_branch else remote_branch
    if local in _local_branches(rw):
        if rw.confirm(T("簽出", "Checkout"),
                      T(f"本地分支「{local}」已存在。要切換到它嗎？",
                        f"Local branch '{local}' already exists. Switch to it?")):
            checkout(rw, local)
        return
    f = Form(rw, T("簽出遠端分支", "Checkout remote branch"), remote_branch)
    f.text("name", T("本地分支名稱", "Local branch name"), local)
    f.check("track", T("追蹤遠端分支 (--track)", "Track remote branch (--track)"), True)
    f.validator = lambda v: _valid_ref_name(v["name"])
    v = f.ask()
    if v:
        args = ["switch", "-c", v["name"]]
        if v["track"]:
            args.append("--track")
        args.append(remote_branch)
        rw.run(args, T("簽出", "Checkout"))


def checkout_commit(rw, ref):
    if rw.confirm(T("簽出提交", "Checkout commit"),
                  T(f"簽出 {ref[:12]} 會進入「分離 HEAD」狀態（不在任何分支上）。是否繼續？",
                    f"Checking out {ref[:12]} puts you in 'detached HEAD' state. Continue?")):
        rw.run(["switch", "--detach", ref], T("簽出", "Checkout"))


def new_branch(rw, start="HEAD"):
    f = Form(rw, T("建立分支", "New branch"))
    f.text("name", T("分支名稱", "Name"), placeholder="feature/my-change")
    f.combo("start", T("起始點", "Start point"), _refs(rw), current=start, editable=True)
    f.check("checkout", T("建立後簽出", "Check out after create"), True)
    f.check("orphan", T("孤立分支 (--orphan，無歷史)", "Orphan branch (no history)"), False)
    f.validator = lambda v: _valid_ref_name(v["name"])
    v = f.ask()
    if not v:
        return
    if v["orphan"]:
        rw.run(["switch", "--orphan", v["name"]], T("建立分支", "New branch"))
    elif v["checkout"]:
        rw.run(["switch", "-c", v["name"], v["start"] or "HEAD"], T("建立分支", "New branch"))
    else:
        rw.run(["branch", v["name"], v["start"] or "HEAD"], T("建立分支", "New branch"))


def rename_branch(rw, name):
    new, ok = QInputDialog.getText(rw, T("重新命名分支", "Rename branch"), T("新名稱：", "New name:"), text=name)
    if ok and new.strip() and new.strip() != name:
        err = _valid_ref_name(new.strip())
        if err:
            rw.error(T("重新命名分支", "Rename branch"), err)
            return
        rw.run(["branch", "-m", name, new.strip()], T("重新命名分支", "Rename branch"))


def delete_branch(rw, name):
    f = Form(rw, T("刪除分支", "Delete branch"), name, ok_text=T("刪除", "Delete"), danger=True)
    f.check("force", T("強制刪除（即使尚未合併）-D", "Force delete even if unmerged (-D)"), False)
    b = next((x for x in rw.repo.branches() if x.name == name), None)
    remote_del = None
    if b and b.upstream:
        remote_del = f.check("remote", T(f"同時刪除遠端分支 {b.upstream}", f"Also delete remote branch {b.upstream}"), False)
    v = f.ask()
    if not v:
        return
    rw.run(["branch", "-D" if v["force"] else "-d", name], T("刪除分支", "Delete branch"))
    if remote_del is not None and v.get("remote"):
        rem, _, br = b.upstream.partition("/")
        rw.run(["push", rem, "--delete", br], T("刪除遠端分支", "Delete remote branch"))


def delete_remote_branch(rw, remote_branch):
    rem, _, br = remote_branch.partition("/")
    if rw.confirm(T("刪除遠端分支", "Delete remote branch"),
                  T(f"要從 {rem} 刪除分支 {br} 嗎？", f"Delete branch {br} from {rem}?"), danger=True):
        rw.run(["push", rem, "--delete", br], T("刪除遠端分支", "Delete remote branch"))


def set_upstream(rw, branch):
    f = Form(rw, T("設定上游分支", "Set upstream"), branch)
    remotes = [b.name for b in rw.repo.remote_branches()]
    f.combo("up", T("上游", "Upstream"), [("", T("（取消上游）", "(unset upstream)"))] + remotes,
            current=next((b.upstream for b in rw.repo.branches() if b.name == branch), ""), editable=True)
    v = f.ask()
    if v is None:
        return
    if v["up"]:
        rw.run(["branch", f"--set-upstream-to={v['up']}", branch], T("設定上游", "Set upstream"))
    else:
        rw.run(["branch", "--unset-upstream", branch], T("取消上游", "Unset upstream"))


def compare_branches(rw, a=None, b=None):
    from .tools import CompareWindow
    CompareWindow(rw, a or "HEAD", b or "").show()


def compare_worktree(rw, sha):
    txt = rw.repo.git("diff", "--no-color", sha, check=False)
    from .tools import DiffWindow
    DiffWindow(rw, T(f"{sha[:8]} ↔ 工作區", f"{sha[:8]} ↔ working tree"), txt).show()


# =========================================================================== remote sync
def fetch(rw, remote=None):
    if remote:
        rw.run(["fetch", "--prune", remote], T(f"提取 {remote}", f"Fetching {remote}"))
    else:
        rw.run(["fetch", "--all", "--prune"], T("提取所有遠端", "Fetching all remotes"))


def fetch_dialog(rw):
    f = Form(rw, T("提取 (fetch)", "Fetch"))
    f.combo("remote", T("遠端", "Remote"), [("--all", T("所有遠端", "All remotes"))] + _remotes(rw))
    f.check("prune", T("清除已刪除的遠端分支 (--prune)", "Prune deleted remote branches (--prune)"), True)
    f.check("prune_tags", T("清除已刪除的標籤 (--prune-tags)", "Prune deleted tags (--prune-tags)"), False)
    f.check("tags", T("提取所有標籤 (--tags)", "Fetch all tags (--tags)"), False)
    f.check("unshallow", T("取得完整歷史 (--unshallow)", "Get full history (--unshallow)"), False)
    f.spin("depth", T("深度 (--depth)", "Depth (--depth)"), 0, 0, 1_000_000, special=T("不限", "unlimited"))
    f.check("recurse", T("包含子模組", "Recurse submodules"), False)
    v = f.ask()
    if not v:
        return
    args = ["fetch"]
    args.append("--all" if v["remote"] == "--all" else v["remote"])
    if v["prune"]: args.append("--prune")
    if v["prune_tags"]: args.append("--prune-tags")
    if v["tags"]: args.append("--tags")
    if v["unshallow"]: args.append("--unshallow")
    if v["depth"]: args.append(f"--depth={v['depth']}")
    if v["recurse"]: args.append("--recurse-submodules")
    if args[1] == "--all":
        args = ["fetch", "--all"] + args[2:]
    rw.run(args, T("提取中…", "Fetching…"))


def pull_dialog(rw):
    branch = rw.repo.current_branch()
    if not branch:
        rw.error(T("拉取", "Pull"), T("目前不在分支上（分離 HEAD）。", "Not on a branch (detached HEAD)."))
        return
    up = next((b.upstream for b in rw.repo.branches() if b.current), "")
    rem_def, _, br_def = up.partition("/") if up else ((_remotes(rw) or ["origin"])[0], "", branch)
    from PySide6.QtCore import QSettings
    mode = QSettings().value("git/pull_mode", "merge")
    f = Form(rw, T("拉取 (pull)", "Pull"), T(f"到目前分支 {branch}", f"into current branch {branch}"))
    f.combo("remote", T("遠端", "Remote"), _remotes(rw), current=rem_def)
    f.combo("branch", T("遠端分支", "Remote branch"),
            [b.name.split("/", 1)[1] for b in rw.repo.remote_branches()], current=br_def or branch, editable=True)
    f.radio("mode", T("整合方式", "Integrate by"), [
        ("merge", T("合併 (merge)", "Merge")), ("rebase", T("變基 (rebase)", "Rebase")),
        ("ff-only", T("僅快轉 (ff-only)", "Fast-forward only"))], default=mode)
    f.check("autostash", T("自動暫存本地變更 (--autostash)", "Auto-stash local changes (--autostash)"), True)
    f.check("prune", "--prune", False)
    f.check("tags", T("同時拉取標籤 (--tags)", "Fetch tags (--tags)"), False)
    f.check("recurse", T("更新子模組 (--recurse-submodules)", "Update submodules"), False)
    v = f.ask()
    if not v:
        return
    args = ["pull", "--" + v["mode"] if v["mode"] != "merge" else "--no-rebase"]
    if v["autostash"]: args.append("--autostash")
    if v["prune"]: args.append("--prune")
    if v["tags"]: args.append("--tags")
    if v["recurse"]: args.append("--recurse-submodules")
    args += [v["remote"], v["branch"]]
    rw.run(args, T("拉取中…", "Pulling…"))


def pull_quick(rw):
    from PySide6.QtCore import QSettings
    mode = QSettings().value("git/pull_mode", "merge")
    up = next((b.upstream for b in rw.repo.branches() if b.current), "")
    if not up:
        pull_dialog(rw)
        return
    args = ["pull", "--autostash", "--no-rebase" if mode == "merge" else "--" + mode]
    rw.run(args, T("拉取中…", "Pulling…"))


def push_dialog(rw, branch=None):
    branch = branch or rw.repo.current_branch()
    remotes = _remotes(rw)
    if not remotes:
        if rw.confirm(T("推送", "Push"), T("此儲存庫沒有遠端。要新增一個嗎？", "No remotes configured. Add one now?")):
            add_remote(rw)
        return
    b = next((x for x in rw.repo.branches() if x.name == branch), None)
    up = b.upstream if b else ""
    rem_def, _, br_def = up.partition("/") if up else (remotes[0], "", branch)
    f = Form(rw, T("推送 (push)", "Push"))
    f.combo("local", T("本地分支", "Local branch"), _local_branches(rw), current=branch)
    f.combo("remote", T("遠端", "Remote"), remotes, current=rem_def)
    f.text("rbranch", T("遠端分支", "Remote branch"), br_def or branch)
    f.check("upstream", T("設定為上游 (-u)", "Set as upstream (-u)"), not up)
    f.radio("force", T("強制", "Force"), [("", T("不強制", "No force")),
                                         ("lease", T("安全強制 (--force-with-lease)", "Force with lease")),
                                         ("force", T("強制覆寫 (--force)", "Force (--force)"))])
    f.check("tags", T("同時推送標籤 (--tags)", "Push tags (--tags)"), False)
    f.check("follow", T("推送相關附註標籤 (--follow-tags)", "Follow tags"), False)
    f.check("all", T("推送所有分支 (--all)", "Push all branches (--all)"), False)
    f.check("noverify", T("略過 pre-push hook (--no-verify)", "Skip pre-push hook"), False)
    f.check("dry", T("試跑 (--dry-run)", "Dry run"), False)
    v = f.ask()
    if not v:
        return
    args = ["push"]
    if v["upstream"]: args.append("-u")
    if v["force"] == "lease": args.append("--force-with-lease")
    elif v["force"] == "force": args.append("--force")
    if v["tags"]: args.append("--tags")
    if v["follow"]: args.append("--follow-tags")
    if v["noverify"]: args.append("--no-verify")
    if v["dry"]: args.append("--dry-run")
    if v["all"]:
        args += ["--all", v["remote"]]
    else:
        args += [v["remote"], f"{v['local']}:{v['rbranch'] or v['local']}"]
    rw.run(args, T("推送中…", "Pushing…"), show_output=v["dry"])


def push_quick(rw):
    b = next((x for x in rw.repo.branches() if x.current), None)
    if not b or not b.upstream:
        push_dialog(rw)
        return
    rw.run(["push"], T("推送中…", "Pushing…"))


# =========================================================================== merge / rebase
def merge(rw, ref=None):
    cur = rw.repo.current_branch() or "HEAD"
    f = Form(rw, T("合併 (merge)", "Merge"), T(f"合併到目前分支 {cur}", f"into current branch {cur}"))
    f.combo("ref", T("要合併的分支/提交", "Branch / commit to merge"), _refs(rw, False), current=ref, editable=True)
    f.radio("mode", T("方式", "Mode"), [
        ("", T("預設（可快轉時快轉）", "Default (fast-forward if possible)")),
        ("--no-ff", T("一律建立合併提交 (--no-ff)", "Always create merge commit (--no-ff)")),
        ("--ff-only", T("僅快轉 (--ff-only)", "Fast-forward only")),
        ("--squash", T("壓縮成一次變更 (--squash)", "Squash (--squash)"))])
    f.combo("strategy", T("衝突偏好 (-X)", "Conflict preference (-X)"),
            [("", T("無", "None")), ("ours", "ours"), ("theirs", "theirs"),
             ("ignore-all-space", "ignore-all-space"), ("patience", "patience")])
    f.check("nocommit", T("不自動提交 (--no-commit)", "Don't commit (--no-commit)"), False)
    f.check("signoff", "--signoff", False)
    f.check("unrelated", T("允許無關歷史 (--allow-unrelated-histories)", "Allow unrelated histories"), False)
    f.text("msg", T("合併訊息（選填）", "Message (optional)"))
    v = f.ask()
    if not v or not v["ref"]:
        return
    args = ["merge"]
    if v["mode"]: args.append(v["mode"])
    if v["strategy"]: args += ["-X", v["strategy"]]
    if v["nocommit"]: args.append("--no-commit")
    if v["signoff"]: args.append("--signoff")
    if v["unrelated"]: args.append("--allow-unrelated-histories")
    if v["msg"]: args += ["-m", v["msg"]]
    args.append(v["ref"])
    rw.run(args, T("合併中…", "Merging…"))


def rebase(rw, onto=None):
    cur = rw.repo.current_branch() or "HEAD"
    f = Form(rw, T("變基 (rebase)", "Rebase"), T(f"將 {cur} 重新套用到…", f"Replay {cur} onto…"))
    f.combo("onto", T("目標", "Onto"), _refs(rw, False), current=onto, editable=True)
    f.check("autostash", "--autostash", True)
    f.check("merges", T("保留合併提交 (--rebase-merges)", "Keep merges (--rebase-merges)"), False)
    f.check("autosquash", T("自動處理 fixup!/squash! (--autosquash)", "Autosquash fixup!/squash!"), False)
    f.check("committer_date", T("保留作者日期為提交日期", "Committer date is author date"), False)
    f.check("interactive", T("互動式（下一步選擇每個提交的動作）", "Interactive (choose actions next)"), False)
    v = f.ask()
    if not v or not v["onto"]:
        return
    if v["interactive"]:
        interactive_rebase(rw, v["onto"], autostash=v["autostash"])
        return
    args = ["rebase"]
    if v["autostash"]: args.append("--autostash")
    if v["merges"]: args.append("--rebase-merges")
    if v["autosquash"]: args += ["-i", "--autosquash"]
    if v["committer_date"]: args.append("--committer-date-is-author-date")
    args.append(v["onto"])
    env = {"GIT_SEQUENCE_EDITOR": "true"} if v["autosquash"] else None
    rw.run(args, T("變基中…", "Rebasing…"), env=env)


def interactive_rebase(rw, base, autostash=True):
    from .tools import InteractiveRebaseDialog
    d = InteractiveRebaseDialog(rw, base)
    if d.exec():
        todo = d.todo_text()
        if not todo.strip():
            return
        path = rw.temp_file(todo, "rebase-todo")
        path_sh = path.replace("\\", "/")
        env = {"GIT_SEQUENCE_EDITOR": f"cp '{path_sh}'"}
        args = ["rebase", "-i"]
        if autostash:
            args.append("--autostash")
        if d.root:
            args.append("--root")
        else:
            args.append(base)
        rw.run(args, T("互動式變基…", "Interactive rebase…"), env=env)


def fixup_commit(rw, sha):
    if not (rw.changes.status and rw.changes.status.staged):
        rw.error("fixup", T("請先暫存要修正進去的變更。", "Stage the changes to fold in first."))
        return
    rw.run(["commit", f"--fixup={sha}"], "commit --fixup")
    if rw.confirm("fixup", T("要立即以 autosquash 變基，把修正合併進該提交嗎？",
                             "Rebase now with autosquash to fold the fixup in?")):
        rw.run(["rebase", "-i", "--autosquash", "--autostash", sha + "~1"], "rebase --autosquash",
               env={"GIT_SEQUENCE_EDITOR": "true"})


# =========================================================================== commits
def cherry_pick(rw, shas):
    f = Form(rw, T("揀選 (cherry-pick)", "Cherry-pick"), "\n".join(s[:10] for s in shas))
    f.check("x", T("在訊息中記錄來源 (-x)", "Record origin in message (-x)"), False)
    f.check("nocommit", T("不自動提交 (--no-commit)", "Don't commit (--no-commit)"), False)
    f.check("signoff", "--signoff", False)
    f.check("ff", T("可快轉時快轉 (--ff)", "Fast-forward if possible (--ff)"), False)
    f.spin("mainline", T("合併提交的主線 (-m)", "Mainline for merge commits (-m)"), 0, 0, 9, special=T("自動", "auto"))
    v = f.ask()
    if not v:
        return
    args = ["cherry-pick"]
    if v["x"]: args.append("-x")
    if v["nocommit"]: args.append("--no-commit")
    if v["signoff"]: args.append("--signoff")
    if v["ff"]: args.append("--ff")
    if v["mainline"]: args += ["-m", str(v["mainline"])]
    else:
        if any(len(rw.repo.git("rev-list", "--parents", "-n1", s).split()) > 2 for s in shas):
            args += ["-m", "1"]
    rw.run(args + shas, T("揀選中…", "Cherry-picking…"))


def revert(rw, shas):
    f = Form(rw, T("還原 (revert)", "Revert"), "\n".join(s[:10] for s in shas))
    f.check("nocommit", T("不自動提交 (--no-commit)", "Don't commit (--no-commit)"), False)
    f.check("signoff", "--signoff", False)
    f.spin("mainline", T("合併提交的主線 (-m)", "Mainline for merge commits (-m)"), 0, 0, 9, special=T("自動", "auto"))
    v = f.ask()
    if not v:
        return
    args = ["revert"]
    if v["nocommit"]: args.append("--no-commit")
    if v["signoff"]: args.append("--signoff")
    if v["mainline"]:
        args += ["-m", str(v["mainline"])]
    elif any(len(rw.repo.git("rev-list", "--parents", "-n1", s).split()) > 2 for s in shas):
        args += ["-m", "1"]
    rw.run(args + shas, T("還原中…", "Reverting…"))


def reset(rw, sha):
    cur = rw.repo.current_branch() or "HEAD"
    f = Form(rw, T("重設 (reset)", "Reset"), T(f"將 {cur} 移動到 {sha[:10]}", f"Move {cur} to {sha[:10]}"))
    f.radio("mode", T("模式", "Mode"), [
        ("--soft", T("軟 (soft)：保留變更於暫存區", "Soft: keep changes staged")),
        ("--mixed", T("混合 (mixed)：保留變更但取消暫存", "Mixed: keep changes unstaged")),
        ("--keep", T("保留 (keep)：保留本地未提交變更", "Keep: keep local uncommitted changes")),
        ("--merge", T("合併 (merge)", "Merge")),
        ("--hard", T("硬 (hard)：捨棄所有變更 ⚠", "Hard: DISCARD all changes ⚠"))], default="--mixed")
    v = f.ask()
    if not v:
        return
    if v["mode"] == "--hard" and not rw.confirm(
            T("硬重設", "Hard reset"), T("所有未提交的變更都會遺失，確定嗎？", "All uncommitted changes will be lost. Sure?"),
            danger=True):
        return
    rw.run(["reset", v["mode"], sha], T("重設中…", "Resetting…"))


def undo_last_commit(rw):
    if not rw.repo.head_valid():
        return
    if rw.confirm(T("復原上次提交", "Undo last commit"),
                  T("將上次提交還原回暫存區（reset --soft HEAD~1）。檔案變更會保留。",
                    "Move the last commit back into the staging area (reset --soft HEAD~1). Your changes are kept.")):
        has_parent = rw.repo.git("rev-parse", "--verify", "-q", "HEAD~1", check=False).strip()
        if has_parent:
            rw.run(["reset", "--soft", "HEAD~1"], T("復原提交", "Undo commit"))
        else:
            rw.run(["update-ref", "-d", "HEAD"], T("復原提交", "Undo commit"))


def new_tag(rw, sha="HEAD"):
    f = Form(rw, T("建立標籤", "New tag"))
    f.text("name", T("標籤名稱", "Name"), placeholder="v1.0.0")
    f.combo("ref", T("提交", "Commit"), _refs(rw), current=sha, editable=True)
    f.multiline("msg", T("附註訊息（填寫即建立附註標籤）", "Message (makes an annotated tag)"), height=70)
    f.check("sign", T("GPG 簽署 (-s)", "GPG sign (-s)"), False)
    f.check("force", T("覆寫已存在的標籤 (-f)", "Replace existing (-f)"), False)
    f.check("push", T("建立後推送到遠端", "Push to remote after create"), False)
    f.validator = lambda v: None if v["name"] else T("請輸入名稱", "Please enter a name")
    v = f.ask()
    if not v:
        return
    args = ["tag"]
    if v["sign"]:
        args.append("-s")
    elif v["msg"].strip():
        args.append("-a")
    if v["msg"].strip() or v["sign"]:
        args += ["-F", rw.temp_file(v["msg"] or v["name"], "TAG_MSG")]
    if v["force"]:
        args.append("-f")
    args += [v["name"], v["ref"] or "HEAD"]
    rw.run(args, T("建立標籤", "Create tag"))
    if v["push"]:
        rem = _remotes(rw)
        if rem:
            rw.run(["push", rem[0], "refs/tags/" + v["name"]], T("推送標籤", "Push tag"))


def delete_tag(rw, name):
    f = Form(rw, T("刪除標籤", "Delete tag"), name, ok_text=T("刪除", "Delete"), danger=True)
    rems = _remotes(rw)
    for r in rems:
        f.check("r:" + r, T(f"同時從 {r} 刪除", f"Also delete from {r}"), False)
    v = f.ask()
    if not v:
        return
    rw.run(["tag", "-d", name], T("刪除標籤", "Delete tag"))
    for r in rems:
        if v.get("r:" + r):
            rw.run(["push", r, "--delete", "refs/tags/" + name], T("刪除遠端標籤", "Delete remote tag"))


def push_tag(rw, name=None):
    rems = _remotes(rw)
    if not rems:
        return
    f = Form(rw, T("推送標籤", "Push tag"), name or T("所有標籤", "All tags"))
    f.combo("remote", T("遠端", "Remote"), rems)
    v = f.ask()
    if v:
        rw.run(["push", v["remote"], "refs/tags/" + name if name else "--tags"], T("推送標籤", "Push tags"))


def edit_note(rw, sha):
    cur = rw.repo.git("notes", "show", sha, check=False)
    f = Form(rw, T("提交備註 (git notes)", "Commit notes"), sha[:10])
    f.multiline("msg", T("備註", "Note"), cur.strip(), height=140)
    f.check("push", T("儲存後推送 notes 到遠端", "Push notes to remote after saving"), False)
    v = f.ask()
    if v is None:
        return
    if v["msg"].strip():
        rw.run(["notes", "add", "-f", "-F", rw.temp_file(v["msg"], "NOTE"), sha], "git notes")
    elif cur.strip():
        rw.run(["notes", "remove", sha], "git notes remove")
    if v["push"] and _remotes(rw):
        rw.run(["push", _remotes(rw)[0], "refs/notes/*"], "push notes")


def restore_file_from(rw, path, rev):
    if rw.confirm(T("還原檔案", "Restore file"),
                  T(f"用 {rev[:12]} 版本覆寫工作區的 {path}？", f"Overwrite {path} in the working tree with {rev[:12]}?"),
                  danger=True):
        rw.run(["restore", f"--source={rev}", "--staged", "--worktree", "--", path], T("還原檔案", "Restore file"))


def save_revision(rw, path, rev):
    out, _ = QFileDialog.getSaveFileName(rw, T("另存檔案", "Save file"), os.path.basename(path))
    if not out:
        return
    try:
        data = rw.repo.git("show", f"{rev}:{path}", binary=True)
        with open(out, "wb") as fh:
            fh.write(data)
    except Exception as e:
        rw.error(T("另存", "Save"), str(e))


def format_patch(rw, shas):
    d = QFileDialog.getExistingDirectory(rw, T("修補檔輸出資料夾", "Output folder for patches"))
    if not d:
        return
    if len(shas) == 1:
        rw.run(["format-patch", "-1", shas[0], "-o", d], "format-patch", show_output=True)
    else:
        rw.run(["format-patch", "-o", d, "--no-walk"] + shas, "format-patch", show_output=True)


def archive(rw, ref="HEAD"):
    f = Form(rw, T("匯出封存檔 (archive)", "Export archive"))
    f.combo("ref", T("版本", "Revision"), _refs(rw), current=ref, editable=True)
    f.combo("fmt", T("格式", "Format"), ["zip", "tar", "tar.gz", "tgz"])
    f.text("prefix", T("目錄前綴 (--prefix)", "Prefix (--prefix)"), rw.repo.name + "/")
    f.path("out", T("輸出檔案", "Output file"), os.path.join(os.path.expanduser("~"), rw.repo.name + ".zip"),
           directory=False, save=True)
    v = f.ask()
    if v and v["out"]:
        rw.run(["archive", f"--format={v['fmt']}", f"--prefix={v['prefix']}", "-o", v["out"], v["ref"]],
               "git archive", refresh=False)


# =========================================================================== stash
def stash_save(rw):
    f = Form(rw, T("暫存變更 (stash)", "Stash changes"))
    f.text("msg", T("說明", "Message"))
    f.check("untracked", T("包含未追蹤檔案 (-u)", "Include untracked (-u)"), True)
    f.check("all", T("包含被忽略的檔案 (--all)", "Include ignored (--all)"), False)
    f.check("keep", T("保留暫存區內容 (--keep-index)", "Keep index (--keep-index)"), False)
    f.check("staged", T("只暫存已暫存的變更 (--staged)", "Only staged changes (--staged)"), False)
    v = f.ask()
    if not v:
        return
    args = ["stash", "push"]
    if v["all"]: args.append("--all")
    elif v["untracked"]: args.append("-u")
    if v["keep"]: args.append("--keep-index")
    if v["staged"]: args.append("--staged")
    if v["msg"]: args += ["-m", v["msg"]]
    rw.run(args, T("暫存中…", "Stashing…"))


def stash_apply(rw, ref="stash@{0}", pop=False):
    f = Form(rw, T("套用 stash", "Apply stash") if not pop else T("取出 stash (pop)", "Pop stash"), ref)
    f.check("index", T("同時還原暫存區狀態 (--index)", "Restore index too (--index)"), False)
    f.check("pop", T("套用後刪除 (pop)", "Delete after applying (pop)"), pop)
    v = f.ask()
    if not v:
        return
    args = ["stash", "pop" if v["pop"] else "apply"]
    if v["index"]: args.append("--index")
    rw.run(args + [ref], T("套用 stash", "Applying stash"))


def stash_drop(rw, ref):
    if rw.confirm(T("刪除 stash", "Drop stash"), T(f"刪除 {ref}？", f"Drop {ref}?"), danger=True):
        rw.run(["stash", "drop", ref], "stash drop")


def stash_branch(rw, ref):
    name, ok = QInputDialog.getText(rw, T("從 stash 建立分支", "Branch from stash"), T("分支名稱：", "Branch name:"))
    if ok and name.strip():
        rw.run(["stash", "branch", name.strip(), ref], "stash branch")


def stash_clear(rw):
    if rw.confirm(T("清除所有 stash", "Clear all stashes"), T("刪除所有 stash 項目？無法復原。", "Delete ALL stashes? Cannot be undone."), danger=True):
        rw.run(["stash", "clear"], "stash clear")


# =========================================================================== remotes
def add_remote(rw):
    f = Form(rw, T("新增遠端", "Add remote"))
    f.text("name", T("名稱", "Name"), "origin" if "origin" not in _remotes(rw) else "")
    f.text("url", "URL", placeholder="https://github.com/user/repo.git")
    f.check("fetch", T("新增後立即提取", "Fetch immediately"), True)
    f.validator = lambda v: None if v["name"] and v["url"] else T("請填寫名稱和 URL", "Name and URL are required")
    v = f.ask()
    if v:
        rw.run(["remote", "add"] + (["-f"] if v["fetch"] else []) + [v["name"], v["url"]], T("新增遠端", "Add remote"))


def edit_remote(rw, name):
    r = next((x for x in rw.repo.remotes() if x["name"] == name), None)
    if not r:
        return
    f = Form(rw, T("編輯遠端", "Edit remote"), name)
    f.text("name", T("名稱", "Name"), name)
    f.text("fetch", T("提取 URL", "Fetch URL"), r["fetch"])
    f.text("push", T("推送 URL", "Push URL"), r["push"])
    v = f.ask()
    if not v:
        return
    if v["fetch"] != r["fetch"]:
        rw.run(["remote", "set-url", name, v["fetch"]], "remote set-url")
    if v["push"] and v["push"] != r["push"]:
        rw.run(["remote", "set-url", "--push", name, v["push"]], "remote set-url --push")
    if v["name"] and v["name"] != name:
        rw.run(["remote", "rename", name, v["name"]], "remote rename")


def remove_remote(rw, name):
    if rw.confirm(T("移除遠端", "Remove remote"), T(f"移除遠端 {name}？", f"Remove remote {name}?"), danger=True):
        rw.run(["remote", "remove", name], "remote remove")


# =========================================================================== bisect
def bisect(rw, what, sha=None):
    if rw.repo.operation_state() != "bisect":
        if what not in ("good", "bad"):
            return
        if not rw.confirm(T("開始二分搜尋", "Start bisect"),
                          T(f"開始 bisect，並將 {sha[:10] if sha else 'HEAD'} 標記為 {what}？",
                            f"Start bisect and mark {sha[:10] if sha else 'HEAD'} as {what}?")):
            return
        rw.run(["bisect", "start"], "bisect start")
    rw.run(["bisect", what] + ([sha] if sha else []), f"bisect {what}", show_output=True)


def bisect_run(rw):
    cmd, ok = QInputDialog.getText(rw, "bisect run", T("測試指令（成功=好，失敗=壞）：", "Test command (exit 0 = good):"))
    if ok and cmd.strip():
        import shlex
        rw.run(["bisect", "run"] + shlex.split(cmd), "bisect run", show_output=True)


# =========================================================================== submodules / worktrees
def add_submodule(rw):
    f = Form(rw, T("新增子模組", "Add submodule"))
    f.text("url", "URL")
    f.text("path", T("路徑", "Path"))
    f.text("branch", T("分支（選填）", "Branch (optional)"))
    f.spin("depth", "--depth", 0, 0, 100000, special=T("不限", "unlimited"))
    v = f.ask()
    if v and v["url"]:
        args = ["submodule", "add"]
        if v["branch"]: args += ["-b", v["branch"]]
        if v["depth"]: args += ["--depth", str(v["depth"])]
        args.append(v["url"])
        if v["path"]: args.append(v["path"])
        rw.run(args, T("新增子模組", "Add submodule"))


def update_submodules(rw, path=None):
    f = Form(rw, T("更新子模組", "Update submodules"), path or T("全部", "All"))
    f.check("init", "--init", True)
    f.check("recursive", "--recursive", True)
    f.check("remote", T("更新到遠端最新 (--remote)", "Update to remote tip (--remote)"), False)
    f.radio("mode", T("方式", "Mode"), [("", "checkout"), ("--merge", "merge"), ("--rebase", "rebase")])
    v = f.ask()
    if not v:
        return
    args = ["submodule", "update"]
    for k in ("init", "recursive", "remote"):
        if v[k]: args.append("--" + k)
    if v["mode"]: args.append(v["mode"])
    if path: args += ["--", path]
    rw.run(args, T("更新子模組", "Updating submodules"))


def add_worktree(rw):
    f = Form(rw, T("新增工作樹", "Add worktree"))
    f.path("path", T("位置", "Location"), os.path.join(os.path.dirname(rw.repo.path), rw.repo.name + "-wt"))
    f.radio("mode", T("分支", "Branch"), [("existing", T("使用現有分支", "Existing branch")),
                                          ("new", T("建立新分支", "Create new branch")),
                                          ("detach", T("分離 HEAD", "Detached HEAD"))])
    f.combo("branch", T("分支 / 起點", "Branch / start point"), _refs(rw), editable=True)
    f.text("newname", T("新分支名稱", "New branch name"))
    f.check("open", T("新增後開啟", "Open after adding"), True)
    v = f.ask()
    if not v or not v["path"]:
        return
    args = ["worktree", "add"]
    if v["mode"] == "new":
        args += ["-b", v["newname"], v["path"], v["branch"] or "HEAD"]
    elif v["mode"] == "detach":
        args += ["--detach", v["path"], v["branch"] or "HEAD"]
    else:
        args += [v["path"], v["branch"]]

    def done(code, *_):
        if code == 0 and v["open"] and rw.main:
            rw.main.open_repo(v["path"])
    rw.run(args, T("新增工作樹", "Add worktree"), done)


# =========================================================================== patches / bundles
def apply_patch_file(rw):
    p, _ = QFileDialog.getOpenFileNames(rw, T("選擇修補檔", "Choose patch files"), "",
                                        "Patch (*.patch *.diff *.eml *.mbox);;All (*)")
    if not p:
        return
    f = Form(rw, T("套用修補檔", "Apply patch"), "\n".join(os.path.basename(x) for x in p))
    f.radio("mode", T("方式", "Mode"), [("am", T("建立提交 (git am)", "Create commits (git am)")),
                                        ("apply", T("只套用到工作區 (git apply)", "Apply to working tree (git apply)")),
                                        ("index", T("套用到工作區與暫存區 (apply --index)", "Apply to tree and index")),
                                        ("check", T("只檢查能否套用 (apply --check)", "Check only (--check)"))])
    f.check("3way", T("三方合併 (-3)", "3-way merge (-3)"), True)
    f.check("signoff", "--signoff (am)", False)
    f.check("reverse", T("反向套用 (-R, apply)", "Reverse (-R, apply)"), False)
    v = f.ask()
    if not v:
        return
    if v["mode"] == "am":
        args = ["am"] + (["-3"] if v["3way"] else []) + (["--signoff"] if v["signoff"] else []) + p
    else:
        args = ["apply"]
        if v["mode"] == "index": args.append("--index")
        if v["mode"] == "check": args += ["--check", "--stat"]
        if v["3way"] and v["mode"] != "check": args.append("-3")
        if v["reverse"]: args.append("-R")
        args += p
    rw.run(args, T("套用修補檔", "Apply patch"), show_output=v["mode"] == "check")


def create_patch_from_changes(rw):
    out, _ = QFileDialog.getSaveFileName(rw, T("儲存修補檔", "Save patch"), "changes.patch", "Patch (*.patch *.diff)")
    if not out:
        return
    f = Form(rw, T("由變更產生修補檔", "Create patch from changes"))
    f.radio("src", T("來源", "Source"), [("wt", T("未暫存的變更", "Unstaged changes")),
                                         ("staged", T("已暫存的變更", "Staged changes")),
                                         ("head", T("所有相對 HEAD 的變更", "All changes vs HEAD"))])
    f.check("binary", "--binary", True)
    v = f.ask()
    if not v:
        return
    args = ["diff"] + (["--binary"] if v["binary"] else [])
    if v["src"] == "staged": args.append("--cached")
    if v["src"] == "head": args.append("HEAD")
    try:
        data = rw.repo.git(*args, binary=True)
        with open(out, "wb") as fh:
            fh.write(data)
    except Exception as e:
        rw.error("diff", str(e))


def bundle(rw):
    f = Form(rw, "git bundle")
    f.radio("op", T("動作", "Action"), [("create", T("建立 bundle", "Create bundle")),
                                        ("verify", T("驗證 bundle", "Verify bundle")),
                                        ("list", T("列出 bundle 中的 refs", "List heads")),
                                        ("unbundle", T("從 bundle 提取", "Fetch from bundle"))])
    f.path("file", T("檔案", "File"), os.path.join(os.path.expanduser("~"), rw.repo.name + ".bundle"),
           directory=False, save=True)
    f.text("refs", T("要包含的 refs（建立時）", "Refs to include (create)"), "--all")
    v = f.ask()
    if not v or not v["file"]:
        return
    import shlex
    if v["op"] == "create":
        rw.run(["bundle", "create", v["file"]] + shlex.split(v["refs"] or "--all"), "bundle create", show_output=True)
    elif v["op"] == "verify":
        rw.run(["bundle", "verify", v["file"]], "bundle verify", show_output=True)
    elif v["op"] == "list":
        rw.run(["bundle", "list-heads", v["file"]], "bundle list-heads", show_output=True)
    else:
        rw.run(["fetch", v["file"], "refs/heads/*:refs/remotes/bundle/*"], "fetch bundle")


def sparse_checkout(rw):
    cur = rw.repo.git("sparse-checkout", "list", check=False)
    enabled = rw.repo.config_get("core.sparseCheckout") == "true"
    f = Form(rw, T("稀疏簽出 (sparse-checkout)", "Sparse checkout"),
             T("只在工作區保留指定的資料夾。", "Only keep selected folders in the working tree."))
    f.radio("op", T("動作", "Action"), [("set", T("啟用 / 設定路徑", "Enable / set paths")),
                                        ("add", T("加入路徑", "Add paths")),
                                        ("reapply", "reapply"),
                                        ("disable", T("停用（還原完整工作區）", "Disable (full checkout)"))])
    f.check("cone", T("Cone 模式（以資料夾為單位，建議）", "Cone mode (folders, recommended)"), True)
    f.multiline("paths", T("路徑（每行一個）", "Paths (one per line)"), cur if enabled else "", height=120)
    v = f.ask()
    if not v:
        return
    paths = [p.strip() for p in v["paths"].splitlines() if p.strip()]
    if v["op"] == "disable":
        rw.run(["sparse-checkout", "disable"], "sparse-checkout disable")
    elif v["op"] == "reapply":
        rw.run(["sparse-checkout", "reapply"], "sparse-checkout reapply")
    else:
        args = ["sparse-checkout", v["op"]]
        if v["op"] == "set":
            args.append("--cone" if v["cone"] else "--no-cone")
        rw.run(args + paths, "sparse-checkout")


def edit_gitignore(rw):
    from .tools import TextFileEditor
    TextFileEditor(rw, os.path.join(rw.repo.path, ".gitignore"), ".gitignore").exec()


def edit_gitattributes(rw):
    from .tools import TextFileEditor
    TextFileEditor(rw, os.path.join(rw.repo.path, ".gitattributes"), ".gitattributes").exec()


def describe(rw):
    rw.run(["describe", "--tags", "--always", "--long", "--dirty"], "git describe", show_output=True, refresh=False)


def shortlog(rw):
    rw.run(["shortlog", "-sne", "--all", "--no-merges"], T("貢獻者統計", "Contributors"), show_output=True, refresh=False)


def count_objects(rw):
    rw.run(["count-objects", "-vH"], "count-objects", show_output=True, refresh=False)


# =========================================================================== sidebar menus
def sidebar_menu(rw, kind, name, data):
    m = QMenu(rw)
    if kind == "group:local":
        m.addAction(icons.icon("plus"), T("建立分支…", "New branch…"), lambda: new_branch(rw))
    elif kind == "group:remote":
        m.addAction(icons.icon("plus"), T("新增遠端…", "Add remote…"), lambda: add_remote(rw))
        m.addAction(icons.icon("fetch"), T("提取全部", "Fetch all"), lambda: fetch(rw))
        m.addAction(T("管理遠端…", "Manage remotes…"), lambda: __import__("gitdesk.tools", fromlist=["x"]).RemotesDialog(rw).exec())
    elif kind == "group:tags":
        m.addAction(icons.icon("plus"), T("建立標籤…", "New tag…"), lambda: new_tag(rw))
        m.addAction(icons.icon("push"), T("推送所有標籤…", "Push all tags…"), lambda: push_tag(rw))
    elif kind == "group:stashes":
        m.addAction(icons.icon("stash"), T("暫存變更…", "Stash changes…"), lambda: stash_save(rw))
        m.addAction(icons.icon("trash"), T("清除全部…", "Clear all…"), lambda: stash_clear(rw))
    elif kind == "group:submodules":
        m.addAction(icons.icon("plus"), T("新增子模組…", "Add submodule…"), lambda: add_submodule(rw))
        m.addAction(icons.icon("refresh"), T("更新全部…", "Update all…"), lambda: update_submodules(rw))
        m.addAction("submodule sync --recursive", lambda: rw.run(["submodule", "sync", "--recursive"], "submodule sync"))
        m.addAction("submodule foreach…", lambda: _submodule_foreach(rw))
    elif kind == "group:worktrees":
        m.addAction(icons.icon("plus"), T("新增工作樹…", "Add worktree…"), lambda: add_worktree(rw))
        m.addAction("worktree prune", lambda: rw.run(["worktree", "prune", "-v"], "worktree prune", show_output=True))
    elif kind == "branch":
        cur = data.current
        if not cur:
            m.addAction(icons.icon("check"), T("簽出", "Checkout"), lambda: checkout(rw, name))
        m.addAction(icons.icon("branch"), T("從此建立分支…", "New branch from here…"), lambda: new_branch(rw, name))
        m.addSeparator()
        if not cur:
            cb = rw.repo.current_branch() or "HEAD"
            m.addAction(icons.icon("merge"), T(f"合併到 {cb}…", f"Merge into {cb}…"), lambda: merge(rw, name))
            m.addAction(icons.icon("rebase"), T(f"將 {cb} 變基到此…", f"Rebase {cb} onto this…"), lambda: rebase(rw, name))
            m.addAction(T("與目前分支比較", "Compare with current"), lambda: compare_branches(rw, "HEAD", name))
        else:
            m.addAction(icons.icon("pull"), T("拉取…", "Pull…"), lambda: pull_dialog(rw))
        m.addAction(icons.icon("push"), T("推送…", "Push…"), lambda: push_dialog(rw, name))
        m.addAction(T("設定上游…", "Set upstream…"), lambda: set_upstream(rw, name))
        if not cur and data.upstream:
            m.addAction(T("快轉到上游", "Fast-forward to upstream"),
                        lambda: rw.run(["fetch", ".", f"{data.upstream}:{name}"], "fast-forward"))
        m.addSeparator()
        m.addAction(T("重新命名…", "Rename…"), lambda: rename_branch(rw, name))
        if not cur:
            m.addAction(icons.icon("trash"), T("刪除…", "Delete…"), lambda: delete_branch(rw, name))
        m.addSeparator()
        m.addAction(T("只顯示此分支歷史", "Show only this branch"),
                    lambda: (rw.show_view("history"), rw.history.set_scope_ref(name)))
        m.addAction(T("複製名稱", "Copy name"), lambda: rw.copy_text(name))
    elif kind == "remote_branch":
        m.addAction(icons.icon("check"), T("簽出為本地分支…", "Checkout as local branch…"), lambda: checkout_remote(rw, name))
        cb = rw.repo.current_branch() or "HEAD"
        m.addAction(icons.icon("merge"), T(f"合併到 {cb}…", f"Merge into {cb}…"), lambda: merge(rw, name))
        m.addAction(icons.icon("rebase"), T(f"將 {cb} 變基到此…", f"Rebase {cb} onto this…"), lambda: rebase(rw, name))
        m.addAction(T("與目前分支比較", "Compare with current"), lambda: compare_branches(rw, "HEAD", name))
        m.addSeparator()
        m.addAction(icons.icon("trash"), T("從遠端刪除…", "Delete from remote…"), lambda: delete_remote_branch(rw, name))
        m.addAction(T("複製名稱", "Copy name"), lambda: rw.copy_text(name))
    elif kind == "remote":
        m.addAction(icons.icon("fetch"), T("提取", "Fetch"), lambda: fetch(rw, name))
        m.addAction(T("清除過期分支 (prune)", "Prune stale branches"), lambda: rw.run(["remote", "prune", name], "remote prune"))
        m.addAction(T("更新預設分支 (set-head --auto)", "Update default branch (set-head)"),
                    lambda: rw.run(["remote", "set-head", name, "--auto"], "remote set-head"))
        m.addAction(T("檢視詳細 (remote show)", "Details (remote show)"),
                    lambda: rw.run(["remote", "show", name], "remote show", show_output=True, refresh=False))
        m.addSeparator()
        m.addAction(T("編輯…", "Edit…"), lambda: edit_remote(rw, name))
        m.addAction(icons.icon("trash"), T("移除…", "Remove…"), lambda: remove_remote(rw, name))
        m.addAction(T("複製 URL", "Copy URL"), lambda: rw.copy_text(data["fetch"]))
    elif kind == "tag":
        m.addAction(T("簽出（分離 HEAD）", "Checkout (detached)"), lambda: checkout_commit(rw, "refs/tags/" + name))
        m.addAction(icons.icon("branch"), T("從此建立分支…", "New branch from here…"), lambda: new_branch(rw, name))
        m.addAction(icons.icon("merge"), T("合併到目前分支…", "Merge into current…"), lambda: merge(rw, name))
        m.addAction(icons.icon("push"), T("推送…", "Push…"), lambda: push_tag(rw, name))
        m.addAction(T("驗證簽章", "Verify signature"),
                    lambda: rw.run(["tag", "-v", name], "tag -v", show_output=True, refresh=False))
        m.addAction(T("匯出封存檔…", "Export archive…"), lambda: archive(rw, name))
        m.addSeparator()
        m.addAction(icons.icon("trash"), T("刪除…", "Delete…"), lambda: delete_tag(rw, name))
        m.addAction(T("複製名稱", "Copy name"), lambda: rw.copy_text(name))
    elif kind == "stash":
        m.addAction(T("套用 (apply)…", "Apply…"), lambda: stash_apply(rw, name, False))
        m.addAction(T("取出 (pop)…", "Pop…"), lambda: stash_apply(rw, name, True))
        m.addAction(T("從此建立分支…", "Create branch…"), lambda: stash_branch(rw, name))
        m.addAction(T("檢視差異", "Show diff"), lambda: _show_stash(rw, name))
        m.addSeparator()
        m.addAction(icons.icon("trash"), T("刪除 (drop)…", "Drop…"), lambda: stash_drop(rw, name))
    elif kind == "submodule":
        m.addAction(T("開啟子模組", "Open submodule"), lambda: rw.main and rw.main.open_repo(os.path.join(rw.repo.path, name)))
        m.addAction(T("初始化 (init)", "Init"), lambda: rw.run(["submodule", "init", "--", name], "submodule init"))
        m.addAction(T("更新…", "Update…"), lambda: update_submodules(rw, name))
        m.addAction("sync", lambda: rw.run(["submodule", "sync", "--", name], "submodule sync"))
        m.addAction(T("設定追蹤分支…", "Set branch…"), lambda: _submodule_set_branch(rw, name))
        m.addAction(T("解除初始化 (deinit)…", "Deinit…"),
                    lambda: rw.confirm("deinit", name) and rw.run(["submodule", "deinit", "-f", "--", name], "submodule deinit"))
        m.addAction(icons.icon("trash"), T("移除子模組…", "Remove submodule…"), lambda: _remove_submodule(rw, name))
    elif kind == "worktree":
        m.addAction(T("開啟", "Open"), lambda: rw.main and rw.main.open_repo(name))
        m.addAction(T("在資料夾中顯示", "Show in folder"), lambda: rw.open_path(name))
        m.addAction(T("鎖定", "Lock") if not data.locked else T("解除鎖定", "Unlock"),
                    lambda: rw.run(["worktree", "unlock" if data.locked else "lock", name], "worktree lock"))
        m.addAction(T("移動…", "Move…"), lambda: _move_worktree(rw, name))
        if os.path.normcase(name) != os.path.normcase(rw.repo.path):
            m.addAction(icons.icon("trash"), T("移除…", "Remove…"),
                        lambda: rw.confirm(T("移除工作樹", "Remove worktree"), name, danger=True) and
                        rw.run(["worktree", "remove", "--force", name], "worktree remove"))
        m.addAction("repair", lambda: rw.run(["worktree", "repair", name], "worktree repair"))
    else:
        return None
    return m


def _show_stash(rw, ref):
    txt = rw.repo.git("stash", "show", "-p", "--include-untracked", ref, check=False) or \
        rw.repo.git("stash", "show", "-p", ref, check=False)
    from .tools import DiffWindow
    DiffWindow(rw, ref, txt).show()


def _submodule_foreach(rw):
    cmd, ok = QInputDialog.getText(rw, "submodule foreach", T("指令：", "Command:"), text="git status --short")
    if ok and cmd.strip():
        rw.run(["submodule", "foreach", "--recursive", cmd], "submodule foreach", show_output=True)


def _submodule_set_branch(rw, path):
    b, ok = QInputDialog.getText(rw, "submodule set-branch", T("分支（空白=預設）：", "Branch (empty = default):"))
    if ok:
        if b.strip():
            rw.run(["submodule", "set-branch", "-b", b.strip(), "--", path], "submodule set-branch")
        else:
            rw.run(["submodule", "set-branch", "-d", "--", path], "submodule set-branch")


def _remove_submodule(rw, path):
    if rw.confirm(T("移除子模組", "Remove submodule"), T(f"從儲存庫移除子模組 {path}？", f"Remove submodule {path} from the repository?"), danger=True):
        rw.run(["submodule", "deinit", "-f", "--", path], "submodule deinit")
        rw.run(["rm", "-f", path], "git rm")


def _move_worktree(rw, path):
    new = QFileDialog.getExistingDirectory(rw, T("新的父資料夾", "New parent folder"), os.path.dirname(path))
    if new:
        rw.run(["worktree", "move", path, os.path.join(new, os.path.basename(path))], "worktree move")
