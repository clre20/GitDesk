"""Turn raw git error output into a plain-language explanation and a fix.

explain(text, args) -> (summary, detail) or None when nothing matched.
"""
from __future__ import annotations

import re

from .i18n import T


def _rules():
    # (regex, summary, detail).  Detail explains *why* and *what to do*.
    return [
        (r"repository '([^']+)' not found|Repository not found|remote: Not Found",
         T("找不到遠端儲存庫", "Remote repository not found"),
         T("伺服器上沒有這個儲存庫。常見原因：\n"
           "• 網址打錯（請檢查帳號名稱、儲存庫名稱的拼字與大小寫）\n"
           "• 這是私人儲存庫，而你尚未登入或沒有存取權限\n"
           "• 儲存庫已被刪除、改名或移轉",
           "The server has no repository at this address. Common causes:\n"
           "• The URL is mistyped (check the owner and repository names)\n"
           "• It is a private repository and you are not signed in or lack access\n"
           "• The repository was deleted, renamed or transferred")),
        (r"Could not resolve host|getaddrinfo|Name or service not known|nodename nor servname",
         T("無法連線到伺服器（找不到主機）", "Cannot reach the server (host not found)"),
         T("網址中的伺服器名稱無法解析。請檢查網址是否打錯（例如 github.com），以及網路是否已連線、是否需要設定代理伺服器。",
           "The server name in the URL could not be resolved. Check the URL for typos (e.g. github.com), "
           "your internet connection, and proxy settings.")),
        (r"could not read Username|terminal prompts disabled",
         T("伺服器要求登入（可能是網址錯誤）", "The server asked for a login (the URL may be wrong)"),
         T("伺服器要求帳號密碼才能存取這個網址。常見原因：\n"
           "• 網址打錯或儲存庫不存在 — GitHub 對不存在的儲存庫也會要求登入，以免洩漏私人儲存庫是否存在\n"
           "• 這是私人儲存庫，需要先登入（建議安裝 Git Credential Manager，或改用 SSH 網址）",
           "The server wants credentials for this address. Common causes:\n"
           "• The URL is mistyped or the repository doesn't exist — GitHub asks for a login even for missing "
           "repositories so it doesn't reveal private ones\n"
           "• It is a private repository and you need to sign in (install Git Credential Manager or use an SSH URL)")),
        (r"Authentication failed|Invalid username or password|HTTP Basic: Access denied",
         T("身分驗證失敗", "Authentication failed"),
         T("帳號或密碼不正確，或伺服器需要登入。GitHub 已不接受帳號密碼，請改用個人存取權杖（Personal Access Token）"
           "或 Git Credential Manager 登入，也可以改用 SSH 網址。",
           "Wrong credentials, or the server requires you to sign in. GitHub no longer accepts passwords: "
           "use a Personal Access Token or Git Credential Manager, or switch to an SSH URL.")),
        (r"Permission denied \(publickey|Host key verification failed",
         T("SSH 金鑰驗證失敗", "SSH key rejected"),
         T("伺服器不接受你的 SSH 金鑰。請確認已建立 SSH 金鑰並加入你的 GitHub/GitLab 帳號，或改用 HTTPS 網址。",
           "The server rejected your SSH key. Make sure you created an SSH key and added it to your account, "
           "or use the HTTPS URL instead.")),
        (r"The requested URL returned error: 403|Permission to .* denied|access denied|You are not allowed to push",
         T("沒有權限", "Permission denied"),
         T("你已登入，但這個帳號沒有寫入這個儲存庫的權限。請確認你是協作者，或改推送到自己的 fork。",
           "You are signed in, but this account cannot write to the repository. Ask to be added as a "
           "collaborator or push to your own fork.")),
        (r"already exists and is not an empty directory",
         T("目標資料夾已存在且不是空的", "Destination folder already exists and is not empty"),
         T("請換一個資料夾名稱，或先清空該資料夾。", "Choose another folder name or empty that folder first.")),
        (r"SSL certificate problem|server certificate verification failed|unable to get local issuer",
         T("SSL 憑證錯誤", "SSL certificate problem"),
         T("無法驗證伺服器的安全憑證，通常是公司網路的代理伺服器或防毒軟體攔截連線所致。請洽網管或設定 http.sslCAInfo。",
           "The server certificate could not be verified, often because a corporate proxy or antivirus intercepts "
           "the connection. Ask your network admin or configure http.sslCAInfo.")),
        (r"Connection timed out|Operation timed out|Connection refused|Failed to connect|Could not connect",
         T("連線逾時或被拒絕", "Connection timed out or refused"),
         T("伺服器沒有回應。請檢查網路、防火牆、代理伺服器設定，或稍後再試。",
           "The server did not respond. Check your network, firewall and proxy, or try again later.")),
        (r"\[rejected\].*\(fetch first\)|\[rejected\].*\(non-fast-forward\)|Updates were rejected because",
         T("推送被拒絕：遠端有你還沒有的提交", "Push rejected: the remote has commits you don't have"),
         T("別人（或你在別台電腦）已經推送了新的提交。請先「拉取」合併遠端的變更，再推送。"
           "若確定要覆蓋遠端，可在推送選項中使用「安全強制 (--force-with-lease)」。",
           "Someone (or you elsewhere) pushed new commits. Pull first to integrate them, then push again. "
           "To overwrite the remote on purpose, use \"Force with lease\" in Push options.")),
        (r"src refspec .* does not match any",
         T("沒有可推送的分支或提交", "Nothing to push for that branch"),
         T("本地沒有這個分支，或分支還沒有任何提交。請先建立提交，或確認分支名稱。",
           "The branch does not exist locally or has no commits yet. Make a commit first or check the branch name.")),
        (r"has no upstream branch|no tracking information|There is no tracking information",
         T("目前分支沒有設定上游", "The current branch has no upstream"),
         T("Git 不知道要跟哪個遠端分支同步。請用「推送選項」勾選「設定為上游 (-u)」，或在分支右鍵選「設定上游」。",
           "Git doesn't know which remote branch to sync with. Use Push options with \"Set as upstream (-u)\", "
           "or right-click the branch → Set upstream.")),
        (r"Need to specify how to reconcile divergent branches|divergent branches",
         T("本地與遠端分支已分岔", "Local and remote branches have diverged"),
         T("兩邊都有對方沒有的提交。請在「拉取選項」選擇合併 (merge) 或變基 (rebase)，或在設定中指定預設拉取方式。",
           "Both sides have commits the other lacks. Choose Merge or Rebase in Pull options, or set the default pull mode in Settings.")),
        (r"Your local changes to the following files would be overwritten|would be overwritten by (checkout|merge)|Please commit your changes or stash them",
         T("有未提交的變更會被覆蓋", "Uncommitted changes would be overwritten"),
         T("這個操作會改到你還沒提交的檔案。請先提交，或用「暫存 (Stash)」把變更收起來，完成後再取出。",
           "This operation would overwrite files you haven't committed. Commit them, or Stash them and pop afterwards.")),
        (r"untracked working tree files would be (overwritten|removed)",
         T("未追蹤的檔案會被覆蓋", "Untracked files would be overwritten"),
         T("目標版本包含和你的未追蹤檔案同名的檔案。請先移動、刪除或提交這些檔案。",
           "The target version contains files with the same names as your untracked files. Move, delete or commit them first.")),
        (r"CONFLICT|Automatic merge failed|could not apply|Resolve all conflicts",
         T("發生衝突", "Conflicts"),
         T("兩邊修改了同一段內容，Git 無法自動合併。請到「工作區變更」解決衝突後，按上方橫幅的「繼續」，或選「中止」放棄。",
           "Both sides changed the same lines and Git can't merge them automatically. Resolve the conflicts in "
           "Local Changes, then press Continue in the banner (or Abort).")),
        (r"refusing to merge unrelated histories",
         T("兩個歷史毫無關聯", "Unrelated histories"),
         T("這兩個分支沒有共同的起點（例如遠端是另外建立的儲存庫）。若確定要合併，請在合併選項勾選「允許無關歷史」。",
           "The branches share no common ancestor (e.g. the remote was created separately). To merge anyway, "
           "tick \"Allow unrelated histories\" in Merge options.")),
        (r"nothing to commit|no changes added to commit",
         T("沒有可提交的內容", "Nothing to commit"),
         T("暫存區是空的。請先把要提交的檔案「暫存」。", "The staging area is empty. Stage the files you want to commit first.")),
        (r"Please tell me who you are|empty ident name|Author identity unknown|unable to auto-detect email",
         T("尚未設定你的名字與 Email", "Your name and email are not set"),
         T("提交需要作者資訊。請到「設定」填寫 user.name 與 user.email。",
           "Commits need an author. Fill in user.name and user.email in Settings.")),
        (r"index\.lock': File exists|Unable to create .*\.lock|cannot lock ref",
         T("儲存庫被其他程式鎖定", "Repository is locked by another process"),
         T("可能有其他 git 程式（終端機、IDE、AI 工具）正在執行。請等它結束再試；若確定沒有，刪除 .git 資料夾中的 .lock 檔即可。",
           "Another git process (terminal, IDE, AI tool) is probably running. Wait for it to finish; if none is, "
           "delete the .lock file inside .git.")),
        (r"a branch named '([^']+)' already exists|already exists$",
         T("名稱已存在", "Name already exists"),
         T("已經有同名的分支或標籤，請換一個名稱。", "A branch or tag with that name already exists. Choose another name.")),
        (r"is not fully merged",
         T("分支尚未合併", "Branch is not fully merged"),
         T("這個分支有尚未合併到其他分支的提交，刪除會遺失它們。若確定要刪除，請勾選「強制刪除」。",
           "The branch has commits not merged anywhere; deleting it would lose them. Tick \"Force delete\" if you are sure.")),
        (r"couldn't find remote ref|Remote branch .* not found",
         T("遠端沒有這個分支", "Remote branch not found"),
         T("遠端儲存庫上沒有指定的分支。請確認分支名稱，或先「提取」更新遠端分支清單。",
           "That branch does not exist on the remote. Check the name or Fetch to refresh the remote branch list.")),
        (r"pathspec '.*' did not match|unknown revision|bad revision|ambiguous argument|not a valid object name|invalid reference",
         T("找不到指定的分支、提交或檔案", "Branch, commit or file not found"),
         T("輸入的名稱不存在，請檢查拼字，或先「提取」取得最新的遠端資料。",
           "The name you entered doesn't exist. Check the spelling or Fetch to get the latest remote data.")),
        (r"is not a valid branch name|not a valid ref name|bad ref",
         T("名稱不合法", "Invalid name"),
         T("分支/標籤名稱不能含空白、~ ^ : ? * [ \\ 或以 / 結尾。", "Branch/tag names cannot contain spaces, ~ ^ : ? * [ \\ or end with /.")),
        (r"not a git repository",
         T("這裡不是 Git 儲存庫", "Not a Git repository"),
         T("此資料夾沒有 .git，可能已被刪除或移動。請重新選擇工作資料夾。",
           "This folder has no .git; it may have been deleted or moved. Choose the working folder again.")),
        (r"exceeds GitHub's file size limit|File .* is \d+\.\d+ MB; this exceeds|large files detected",
         T("檔案太大", "File too large"),
         T("GitHub 單一檔案上限 100 MB。請用 Git LFS 追蹤大檔案（儲存庫 → Git LFS），或把它移出版本控制。",
           "GitHub limits files to 100 MB. Track large files with Git LFS (Repository → Git LFS) or remove them from version control.")),
        (r"gpg failed to sign|secret key not available|error: gpg",
         T("GPG 簽章失敗", "GPG signing failed"),
         T("找不到可用的 GPG 金鑰或 GPG 未安裝。取消勾選「GPG 簽章」，或設定 user.signingkey。",
           "No usable GPG key or GPG is not installed. Untick \"GPG sign\" or configure user.signingkey.")),
        (r"hook declined|pre-commit hook|pre-push hook|hook .* failed",
         T("Hook 拒絕了這個操作", "A hook rejected the operation"),
         T("儲存庫的 hook 腳本（例如格式檢查、測試）回報失敗。請依下方訊息修正，或勾選「略過 hooks」。",
           "A repository hook (e.g. lint or tests) failed. Fix what it reports below, or tick \"No verify\".")),
        (r"You are in the middle of|already in progress|There is no merge to abort|No rebase in progress",
         T("有其他操作正在進行或狀態不符", "Another operation is in progress (or none is)"),
         T("請先完成或中止目前的合併／變基／揀選（見上方橫幅），再執行此操作。",
           "Finish or abort the current merge / rebase / cherry-pick (see the banner) before doing this.")),
        (r"Failed to start git|No such file or directory: 'git'|git: command not found",
         T("找不到 git", "git not found"),
         T("請安裝 Git（Windows：Git for Windows），或在「設定」指定 git 執行檔路徑。",
           "Install Git (Windows: Git for Windows) or set the git executable path in Settings.")),
    ]


def explain(text: str):
    if not text:
        return None
    for pattern, summary, detail in _rules():
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            return summary, detail
    return None


def show_git_error(parent, title: str, text: str):
    """Message box: plain-language cause first, raw git output underneath."""
    from PySide6.QtWidgets import QMessageBox
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(title)
    raw = (text or "").strip()
    ex = explain(raw)
    lines = raw.splitlines()
    short_raw = "\n".join(lines[-8:])
    url = re.search(r"(https?://[^\s'\"]+|git@[^\s'\"]+|ssh://[^\s'\"]+)", raw)
    url_line = (T("網址：", "URL: ") + url.group(1).rstrip("/") + "\n\n") if url else ""
    if ex:
        box.setText(f"<b>{ex[0]}</b>")
        box.setInformativeText(ex[1] + "\n\n" + url_line + T("Git 原始訊息：", "Git output:") + "\n" + short_raw)
    else:
        box.setText(f"<b>{T('操作失敗', 'The operation failed')}</b>")
        box.setInformativeText(short_raw or T("命令失敗", "Command failed"))
    if len(lines) > 8:
        box.setDetailedText(raw)
    box.setStandardButtons(QMessageBox.Ok)
    box.exec()
