# GitDesk

圖形化 Git 用戶端 · Cross-platform graphical Git client
介面支援 **繁體中文 / English**。

## 功能 / Features

| 類別 | 內容 |
|---|---|
| 工作區 | 檔案 / **區塊 / 單行** 暫存、取消暫存、捨棄；提交（修訂、簽署、GPG、略過 hooks、空提交）、提交並推送、.gitignore、git mv、rm --cached、assume-unchanged / skip-worktree、chmod |
| 歷史 | 分支圖、搜尋（訊息/作者/-S/-G/路徑/日期/SHA）、提交詳情（簽章、notes）、兩提交比較、分頁載入 |
| 分支 | 建立/簽出/重新命名/刪除（含遠端）、上游設定、快轉、孤立分支、分支比較 |
| 整合 | merge（--no-ff/--ff-only/--squash/-X）、rebase、**互動式 rebase**（pick/reword/edit/squash/fixup/drop/排序）、autosquash、cherry-pick、revert、reset（soft/mixed/keep/merge/hard） |
| 衝突 | 內建三方衝突編輯器、ours/theirs、mergetool；merge/rebase/cherry-pick/revert/am 進行中的繼續/略過/中止橫幅 |
| 遠端 | fetch/pull/push 全選項（prune、tags、force-with-lease、upstream、dry-run…）、遠端管理 |
| 其他 | stash（含未追蹤、keep-index、staged、branch）、tags（附註/簽署/推送/驗證）、子模組、工作樹、bisect（含 run）、blame、檔案歷史、reflog、grep、LFS、hooks、git config（local/global/worktree）、sparse-checkout、patch（format-patch/am/apply）、archive、bundle、gc/fsck/repack/maintenance、clean、describe、shortlog |

## 安裝 / Install

需要先安裝 Git · Requires Git: Windows → [Git for Windows](https://git-scm.com/download/win)；Linux → `sudo apt install git`

- **Linux (Debian/Ubuntu)**：`sudo apt install ./gitdesk_1.0.2_amd64.deb`，之後從應用程式選單或執行 `gitdesk` 開啟。
  其他發行版：解壓 `GitDesk-1.0.2-linux-x86_64.tar.gz`，執行 `GitDesk/gitdesk`。
- **Windows 11**：執行 `GitDesk-Setup-1.0.2.exe`。