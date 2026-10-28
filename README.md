# GitDesk

跨平台（Windows 11 / Linux）圖形化 Git 用戶端 · Cross-platform graphical Git client
介面支援 **繁體中文 / English**（設定 → 語言，或啟動畫面右上角切換）。

## 使用方式 / How it works

1. **啟動時先選工作資料夾** — 已是 Git 儲存庫就直接繼續；不是的話會自動 `git init`（可選初始分支、預設 .gitignore、初始提交）。也可以從網址 clone。
   *Pick the working folder at launch — existing repos open directly, other folders get `git init`.*
2. **自動同步** — 其他程式（終端機、AI 代理、IDE）對儲存庫的任何變更（commit、branch、stash、檔案修改、merge/rebase 狀態…）都會即時反映在畫面上，不需手動重新整理。
   *Live sync: changes made by any other tool appear immediately.*
3. 介面上沒有的 git 指令，可在下方「指令記錄與終端機」直接輸入執行。

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

- **Linux (Debian/Ubuntu)**：`sudo apt install ./gitdesk_1.0.0_amd64.deb`，之後從應用程式選單或執行 `gitdesk` 開啟。
  其他發行版：解壓 `GitDesk-1.0.0-linux-x86_64.tar.gz`，執行 `GitDesk/gitdesk`。
- **Windows 11**：執行 `GitDesk-Setup-1.0.0.exe`（可選加入資料夾右鍵「Open with GitDesk」）。

## 建置安裝檔 / Build installers

```bash
# Linux → dist/gitdesk_<ver>_amd64.deb + dist/GitDesk-<ver>-linux-x86_64.tar.gz
bash packaging/linux/build_linux.sh
```

```powershell
# Windows（需 Python 3.10+ 與 Inno Setup 6）→ dist\GitDesk-Setup-<ver>.exe + portable zip
.\packaging\windows\build_windows.ps1
```

或推送 `v*` 標籤到 GitHub，`.github/workflows/build.yml` 會同時建置兩個平台的安裝檔並建立 Release。

## 從原始碼執行 / Run from source

```bash
pip install -r requirements.txt
python run_gitdesk.py            # 或 python run_gitdesk.py /path/to/folder
```

## 專案結構 / Layout

```
gitdesk/
  __main__.py    啟動流程（先選資料夾）、askpass
  startup.py     選資料夾 / git init / clone
  git.py         git 指令封裝（同步與非同步）
  watcher.py     檔案系統監看 + 指紋輪詢 → 自動重新整理
  repowidget.py  單一儲存庫畫面、操作佇列、狀態橫幅
  changes.py     工作區與提交
  history.py     歷史與分支圖（graph.py）
  diffview.py    差異檢視與區塊/單行暫存
  actions.py     所有 git 操作對話框
  tools.py       互動式 rebase、衝突編輯器、blame、reflog、LFS、hooks、config…
packaging/       PyInstaller spec、Linux .deb、Windows Inno Setup
```
