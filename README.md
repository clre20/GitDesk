# GitDesk

**簡單好用的 Git 圖形介面，支援 Windows 與 Linux。**
不用背指令，用滑鼠就能完成提交、推送、分支、合併等所有 Git 操作。

介面支援 **繁體中文 / English** · [English summary](#english)

---

## 下載

到 **[最新版本下載頁](https://github.com/clre20/GitDesk/releases/latest)**，依你的電腦選一個檔案：

| 你的電腦 | 下載這個 | 說明 |
|---|---|---|
| **Windows 10 / 11** | `GitDesk-Setup-x.x.x.exe` | ✅ 推薦。安裝版，之後可自動更新 |
| Windows（不想安裝） | `GitDesk-x.x.x-windows-x64-portable.zip` | 解壓縮後直接執行 `GitDesk.exe`，可放隨身碟 |
| **Ubuntu / Debian / Linux Mint** | `gitdesk_x.x.x_amd64.deb` | ✅ 推薦。安裝版，之後可自動更新 |
| 其他 Linux（Fedora、Arch…） | `GitDesk-x.x.x-linux-x86_64.tar.gz` | 解壓縮後執行 `GitDesk/gitdesk` |

> ! **電腦需要先安裝 Git**
> - Windows：安裝 [Git for Windows](https://git-scm.com/download/win)（一路按「下一步」即可）
> - Linux：在終端機執行 `sudo apt install git`

## 安裝

**Windows**
1. 執行 `GitDesk-Setup-x.x.x.exe`，先選擇語言，再照畫面按「下一步」。
2. 如果出現「Windows 已保護您的電腦」，點 **其他資訊 → 仍要執行**。（因為程式沒有購買數位簽章，這是正常的）
3. 可勾選「在資料夾右鍵選單加入 Open with GitDesk」，之後在資料夾按右鍵就能直接開啟。

**Ubuntu / Debian**
在下載的資料夾開啟終端機，執行：
```bash
sudo apt install ./gitdesk_x.x.x_amd64.deb
```
之後從應用程式選單找到 **GitDesk** 開啟。

## 開始使用

1. **選擇語言**（只有第一次會問，之後可在「設定」更改）
2. **選擇工作資料夾**
   - 已經是 Git 專案 → 直接開啟
   - 一般資料夾 → 自動幫你建立成 Git 專案（`git init`）
   - 想下載別人的專案 → 按「從網址複製 (clone)」，貼上 GitHub 網址
3. 進入主畫面就可以開始工作了

## 常用操作

| 我想要… | 怎麼做 |
|---|---|
| 看我改了哪些檔案 | 左側點 **工作區變更**，點檔案就會在右邊顯示差異 |
| 把修改存成一個版本（提交） | 勾選要提交的檔案（按兩下或「全部暫存」）→ 下方輸入說明 → 按 **提交** |
| 只提交檔案中的一部分 | 在右邊差異畫面選取紅/綠色的行 → 按 **暫存選取行** |
| 上傳到 GitHub | 工具列 **推送** |
| 取得別人的最新修改 | 工具列 **拉取** |
| 開新分支 / 切換分支 | 工具列 **分支**；左側分支按兩下即可切換 |
| 合併分支 | 工具列 **合併**，選擇要合併進來的分支 |
| 暫時收起修改 | 工具列 **暫存 (Stash)**，之後按 **取出** 拿回來 |
| 剛剛的提交想反悔 | 工具列 **復原提交**（修改內容會保留） |
| 看歷史紀錄 | 左側點 **歷史記錄**，可搜尋訊息、作者、檔案 |
| 找出某行是誰改的 | 在檔案上按右鍵 → **逐行追溯 (blame)** |

**小提示**
- 幾乎所有東西都可以按 **右鍵** 看到更多操作。
- 合併時發生衝突，畫面上方會出現黃色提示，照著按「解決 → 繼續」即可。
- 介面上找不到的 Git 指令，可以在最下方的指令列直接輸入。

## 自動同步

你在終端機、VS Code 或 AI 工具裡對專案做的任何改動，GitDesk 畫面都會**自動更新**，不用手動重新整理。右下角的「● 自動同步中」代表正在監看。

## ⬆更新

GitDesk 啟動時會自動檢查有沒有新版本：
- **安裝版**：跳出提示後按「下載並安裝」，會更新並重新開啟。
- **免安裝版**：會帶你到下載頁，下載新版後取代舊資料夾即可。

也可以從選單 **說明 → 檢查更新** 手動檢查；不想自動檢查可以在 **設定** 關閉。

## 常見問題

**Q：打開時說「找不到 git」？**
A：電腦還沒安裝 Git，請參考上面「下載」區的說明安裝，裝好後重新開啟 GitDesk。

**Q：推送或複製時要我登入 / 說驗證失敗？**
A：GitHub 已經不接受密碼登入。Windows 安裝 Git for Windows 時內建的登入工具會跳出瀏覽器讓你登入；Linux 可以改用 [個人存取權杖 (Token)](https://github.com/settings/tokens) 或 SSH 金鑰。

**Q：複製時說「找不到遠端儲存庫」？**
A：通常是網址打錯，請檢查帳號和專案名稱；如果是私人專案，需要先登入並有存取權限。

**Q：推送被拒絕？**
A：代表網路上的版本比你的新，先按 **拉取** 再 **推送**。

**Q：怎麼切換中文 / 英文？**
A：工具列右上角 **設定 → 語言**，重新開啟後生效。

遇到其他問題，歡迎到 [Issues](https://github.com/clre20/GitDesk/issues) 回報，附上截圖會更好處理。

---

## English

GitDesk is a graphical Git client for Windows and Linux, in English and Traditional Chinese.

- **Download:** get the [latest release](https://github.com/clre20/GitDesk/releases/latest) — `GitDesk-Setup-*.exe` for Windows, `gitdesk_*_amd64.deb` for Ubuntu/Debian (portable `.zip` / `.tar.gz` also available). [Git](https://git-scm.com/downloads) must be installed.
- **Start:** pick your language, then a working folder. Existing repositories open directly; plain folders are turned into one (`git init`); or clone from a URL.
- **Everything Git does is in the UI:** staging by file, hunk or line, commit graph, branches, merge, (interactive) rebase, conflict editor, stash, tags, remotes, submodules, worktrees, bisect, blame, reflog, LFS, hooks, config and more. Anything else can be typed into the built-in command line.
- **Live sync:** changes made by terminals, IDEs or AI agents show up automatically.
- **Updates:** checked at startup; installed copies update themselves after you agree.

---