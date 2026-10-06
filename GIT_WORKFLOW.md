# 🦉 单词助手 · GitHub 提交 / 构建工作流说明

> 本文记录本仓库（`liangzhovo/wordassistant-ios`）从本地提交到 GitHub、触发 CI 构建、发布产物的完整流程，以及期间踩过的坑和解决方案。

---

## 1. 整体架构

```
本地 Windows ──git push──▶ GitHub (liangzhovo/wordassistant-ios) ──▶ GitHub Actions (macOS runner)
     ▲                                                            │
     │                        ◀── 下载 IPA ──────────────────────┘
     │
     └── Release data-v1（词典 103MB，供 CI 下载）
     └── Release ipa-latest（最新 IPA，供用户下载）
```

- **代码仓库**：https://github.com/liangzhovo/wordassistant-ios
- **自动构建**：推送 `ios-app/**` 或 `.github/workflows/*.yml` 变更即触发
- **产物**：未签名 IPA 自动上传到 Release `ipa-latest` + Actions Artifact

---

## 2. 前置配置（一次性的）

### 2.1 GitHub 账号（避免"选择账号"弹窗）

Windows 凭据管理器里之前同时存了 `jackit827` 和 `liangzhovo` 两个账号，导致 Git Credential Manager 每次弹窗让你选。已解决：

1. **删除多余账号凭据**（只保留 liangzhovo）：
   ```bat
   cmdkey /delete:"git:https://jackit827@github.com"
   cmdkey /delete:"LegacyGeneric:target=GitHub for Visual Studio - https://jackit827@github.com/"
   ```
2. **git 全局配置指定默认用户名**（`C:\Users\liang\.gitconfig`）：
   ```ini
   [credential "https://github.com"]
       username = liangzhovo
   [user]
       name = wordassistant
       email = wordassistant@users.noreply.github.com
   ```
3. **gh CLI 登录**（`%APPDATA%\GitHub CLI\hosts.yml` 写入 oauth_token，gh 不再问）。
4. **兜底**：环境变量 `GCM_INTERACTIVE=never`（`setx GCM_INTERACTIVE never`），Git Credential Manager 永不弹交互窗。

> 验证：`git credential fill` 输入 `protocol=https / host=github.com` 应静默返回 `username=liangzhovo`。

### 2.2 代理（直连 GitHub 慢/不通时）

本机对 GitHub 直连下载很慢（~50KB/s），但 xray 代理快（~100MB/s）。需要时给命令加代理：

```bat
set HTTP_PROXY=http://127.0.0.1:10808
set HTTPS_PROXY=http://127.0.0.1:10808
git push origin main
```

或单条命令：
```bat
git -c http.proxy=http://127.0.0.1:10808 push origin main
```

> 代理失效特征：`git push` / `git ls-remote` 长时间无响应或 `TLS handshake failed`（curl exit 35）。
> 换可用节点后再执行即可。

---

## 3. 本地提交

仓库在 `E:\app\单词助手`，**当前分支 `main`**（与 GitHub 默认分支一致，工作流监听 `main`）。

**流程**（每次改代码后）：

```bat
cd /d E:\app\单词助手

:: 1) 查看改动
git status
git diff --stat

:: 2) 暂存（只加想提交的文件；注意中文文件名要加引号）
git add -- "ios-app/WordAssistant/Api.swift" "app.py"

:: 3) 提交（写清改了什么、为什么）
git commit -m "描述本次改动，如：修复xx问题/新增xx功能"

:: 4) 推送（直连不行就走代理）
git push origin main
```

**提交信息约定**：一句中文，说明"改了什么、解决什么问题"。例：
- `修复 iOS 真机搜索 404：bootstrap 增加 .db 资源枚举兜底与坏库重拷校验`
- `词典升级为 ECDICT v2 修复版：修复无音标词组被丢弃、变体词音标错误`

**不该提交的东西**（已在 `.gitignore`，或保持 untracked）：
- `dist/`（构建产物）
- `简明英汉字典增强版.db`（103MB 词典，走 Release 不放仓库）
- `_diag_*.py` / `diag*.txt` / `rebuild*.txt` / `*.db.small.new`（临时诊断文件）
- `.local/`（gh 本地状态）

---

## 4. GitHub 侧操作

### 4.1 创建仓库（一次性）

```bat
:: 用凭据里的 token（可通过 git credential fill 取出）
curl -X POST -H "Authorization: Bearer <token>" https://api.github.com/user/repos ^
  -d "{\"name\":\"wordassistant-ios\",\"private\":false,\"description\":\"单词助手 iOS 离线词典\"}"
git remote add origin https://github.com/liangzhovo/wordassistant-ios.git
git branch -m main          :: 本地分支改名为 main
git push -u origin main
```

### 4.2 上传词典到 Release（data-v1）

词典 103MB 不入仓库，放 Release 供 CI 下载：

```bat
set GH_TOKEN=<token>
gh release upload data-v1 "android-app\app\src\main\assets\简明英汉字典增强版.db" --clobber --repo liangzhovo/wordassistant-ios
```

**坑：中文文件名会被 GitHub 自动改成 `default.db`** —— 这是正常现象，不要改名；
`ios-app/scripts/fetch-db.sh` 已支持按 `*.db` 兜底下载并改名为目标文件名。

验证：
```bat
gh release view data-v1 --repo liangzhovo/wordassistant-ios
:: 资产大小应为 103 MB 级；若是 43 MB 级说明还是旧版，需重传
```

### 4.3 触发 CI 构建

- **自动触发**：推送 `ios-app/**` 或 `.github/workflows/build-ipa.yml` 的改动
- **手动触发**：GitHub Actions 页面 → 选 `Build iOS IPA` → Run workflow

构建产物（未签名 IPA，约 47MB）自动：
1. 上传到 Release `ipa-latest`（固定标签，最新版覆盖）
2. 上传到 Actions Artifact `WordAssistant-unsigned-ipa`

下载：
```bat
:: 浏览器/curl 直接下 Release 最新版
curl -L -o WordAssistant-unsigned.ipa ^
  https://github.com/liangzhovo/wordassistant-ios/releases/download/ipa-latest/WordAssistant-unsigned.ipa
```

---

## 5. CI 工作流做了什么（.github/workflows/build-ipa.yml）

```
1. checkout（lfs: false）
2. fetch-db.sh   —— 优先本地词典 → Release data-v1 下载 → 兜底精简库 .small
3. brew install xcodegen
4. xcodegen generate
   + perl 强制 objectVersion = 56（XcodeGen 2.46 默认生成 Xcode16 格式 77，
     runner 默认 Xcode 15.4 读不了 —— 这是最初构建失败 #1~#3 的根因）
5. xcodebuild archive（CODE_SIGNING_ALLOWED=NO，未签名）
6. 打包 IPA：zip 根必须为 Payload/（标准 IPA 结构，否则签名工具报
   "No Payload directory found" —— #11 的坑），并 unzip 校验结构
7. gh release upload → ipa-latest（--clobber 覆盖）
8. upload-artifact
```

---

## 6. 常见问题速查

| 现象 | 原因 / 解决 |
|---|---|
| git push 卡住没反应 | 直连 GitHub 慢/断；`git -c http.proxy=http://127.0.0.1:10808 push` 走代理 |
| 弹"选择 GitHub 账号" | 凭据库里多个账号；删掉多余的，git config 指定 username |
| 构建失败 `Xcode project file format (77)` | XcodeGen 新格式；工作流已用 perl 强制 `objectVersion = 56` |
| iLoader 报 `No Payload directory` | IPA zip 根缺 Payload/；工作流已修正并从 CI 校验 |
| 手机上全部词搜不到（404） | `Bundle.main.url(forResource: 中文名)` 真机 miss → 已加 .db 枚举兜底 + 坏库重拷（提交 18e84f1） |
| Release 词典 asset 叫 default.db | GitHub 对中文文件名改名，正常；fetch-db.sh 按 *.db 兜底 |
| IPA 大小 47MB / 词典 103MB | 正确（ECDICT v2 完整版压缩后如此）；旧版 174MB 是 488MB 老词典，已废弃 |

---

## 7. 常用命令速查

```bat
:: 状态 / 提交
git status && git diff --stat
git add -- <files> && git commit -m "message"
git push origin main                    :: 或带代理：git -c http.proxy=... push

:: 看远端状态
git log --oneline -5
git rev-parse HEAD origin/main

:: Release / 构建
gh run list --repo liangzhovo/wordassistant-ios
gh release view ipa-latest --repo liangzhovo/wordassistant-ios
gh release upload data-v1 <db> --clobber --repo liangzhovo/wordassistant-ios

:: 拿 token（脚本用）
git credential fill   :: 输入 protocol=https / host=github.com
```

---

*文档维护：随流程演进更新；遇到新坑请补充到第 6 节。*
