# 🦉 单词助手 — iOS (IPA) 构建

离线单词助手：搜索、生词本、SM-2 间隔重复复习、错题本、打卡、笔记、导入导出。
本仓库同时包含 Android 版（`android-app/`）与 Python Web 版（`app.py`）源码。

iOS 版是**全平台一致的离线应用**：

- 前端复用 Android 版的 `index.html`（单页应用）
- 后端将 Python Flask 的 27 个接口**全量移植为 Swift**，直接查询内置 SQLite 词典
- WKWebView 通过自定义 `wordapp://` scheme 提供页面与 API，无网络请求、无后台服务器，App Store 合规

---

## 目录结构

```
ios-app/
├── project.yml                 # XcodeGen 工程定义（CI 用它生成 .xcodeproj）
├── scripts/
│   ├── fetch-db.sh             # 下载/回退词典（CI 与本地共用）
│   ├── make_index.py           # 由 Android 前端生成 iOS 版前端（body 走 query、去 lookbehind）
│   └── make_icons.py           # 由 Android 图标生成 iOS AppIcon
└── WordAssistant/
    ├── AppDelegate.swift
    ├── ViewController.swift    # WKWebView + JS 桥接（模拟 window.Android）+ 启动画面
    ├── SchemeHandler.swift     # wordapp:// 自定义 scheme（页面 + API 路由）
    ├── Database.swift          # SQLite 封装 + init_db 移植 + 学习日志
    ├── Api.swift               # 27 个接口全量移植（对应 app.py）
    ├── Utils.swift             # 释义清洗 / SM-2 / 日期（纯逻辑）
    ├── Speech.swift            # AVSpeechSynthesizer 发音
    ├── Reminder.swift          # UNUserNotificationCenter 每日提醒
    ├── Resources/index.html    # iOS 版前端（脚本生成）
    └── Assets.xcassets/        # AppIcon（脚本生成）
```

---

## 词典数据（重要）

| 文件 | 大小 | 词条 | 说明 |
|---|---|---|---|
| `简明英汉字典增强版.db` | 488MB | 332 万 | **完整版**，不入库，由 GitHub Release (`data-v1`) 提供，CI 自动下载 |
| `简明英汉字典增强版.db.small` | 82MB | 98 万 | **精简版**，随仓库提交，作为构建回退（功能一致） |

`ios-app/scripts/fetch-db.sh` 的优先级：本地已有完整版 → Release 下载 → 回退精简库。
首次在手机上启动时，应用会把词典复制到 App Support 并自动建索引（完整版约需 30~60 秒，有启动画面提示）。

> Release 资产下载不计入 Git LFS 流量；如需更新词典，用 `gh release upload data-v1 <新文件> --clobber` 覆盖即可。

---

## 用 GitHub Actions 构建 IPA

1. 推送本仓库到 GitHub（`main` 分支）。
2. 有完整词典时先上传 Release（否则自动用精简库）：
   ```bash
   gh release create data-v1 android-app/app/src/main/assets/简明英汉字典增强版.db
   ```
3. 触发构建：推送 `ios-app/**` 变更会自动触发，或到 Actions 页面手动 `Run workflow`。
4. 构建产出：**WordAssistant-unsigned.ipa**（未签名，约 200MB），在 Actions 运行的 Artifacts 里下载。

工作流：`.github/workflows/build-ipa.yml`（macOS runner → xcodegen → xcodebuild archive → zip 打包）。

---

> **构建流水线注意**（已内置在 `.github/workflows/build-ipa.yml` / `ios-app/scripts/fetch-db.sh`）：
> - XcodeGen 2.46 默认生成 Xcode 16 的工程格式（objectVersion 77），runner 默认 Xcode 15.4 读不了。
>   工作流在 `xcodegen generate` 后用 perl 把 `objectVersion` 强制改为 56（Xcode 14+ 全兼容）。
> - GitHub 上传中文资产名时可能被改成 `default.db`，`fetch-db.sh` 已按 `*.db` 兜底下载并改名为
>   `简明英汉字典增强版.db`，所以 Release 资产名不影响构建。
> - 完整词典由 Release `data-v1` 提供（当前资产约 466MB）；未上传时自动回退仓库内 82MB 精简库（功能一致）。

## 安装到 iPhone（无开发者账号）

未签名 IPA **不能直接安装**到普通 iPhone。任选其一：

- **爱思助手 / Sideloadly / AltStore**：用你的 Apple ID 免费自签安装，7 天过期需重签；
- **开发者账号（推荐）**：配置签名后走 TestFlight / 企业分发 / App Store。

### 开启正式签名

1. Apple Developer 后台创建 App ID `com.wordassistant.app`、下载证书与描述文件；
2. 在仓库 Settings → Secrets 添加：
   - `APPLE_CERT_P12`（证书 .p12 的 base64）
   - `APPLE_CERT_P12_PASSWORD`
   - `APPLE_PROFILE`（描述文件 .mobileprovision 的 base64）
   - `TEAM_ID`（你的 Team ID）
3. 复制下面的工作流为 `.github/workflows/build-ipa-signed.yml`：

```yaml
name: Build Signed IPA
on: workflow_dispatch
jobs:
  build:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - name: Prepare dictionary DB
        run: bash ios-app/scripts/fetch-db.sh
        env: { GITHUB_REPOSITORY: ${{ github.repository }}, GH_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
      - name: Install XcodeGen
        run: brew install xcodegen
      - name: Decode signing assets
        run: |
          echo "$APPLE_CERT_P12" | base64 -d > /tmp/cert.p12
          echo "$APPLE_PROFILE" | base64 -d > /tmp/profile.mobileprovision
          mkdir -p ~/Library/MobileDevice/Provisioning\ Profiles
          cp /tmp/profile.mobileprovision ~/Library/MobileDevice/Provisioning\ Profiles/
          security create-keychain -p temp build.keychain
          security default-keychain -s build.keychain
          security unlock-keychain -p temp build.keychain
          security import /tmp/cert.p12 -k build.keychain -P "$APPLE_CERT_P12_PASSWORD" -T /usr/bin/codesign -T /usr/bin/xcodebuild
          security set-key-partition-list -S apple-tool:,apple: -s -k temp build.keychain
        env: { APPLE_CERT_P12: ${{ secrets.APPLE_CERT_P12 }}, APPLE_CERT_P12_PASSWORD: ${{ secrets.APPLE_CERT_P12_PASSWORD }}, APPLE_PROFILE: ${{ secrets.APPLE_PROFILE }} }
      - name: Build + export
        working-directory: ios-app
        run: |
          xcodegen generate
          xcodebuild archive -project WordAssistant.xcodeproj -scheme WordAssistant -configuration Release \
            -destination 'generic/platform=iOS' -archivePath build/WordAssistant.xcarchive \
            -allowProvisioningUpdates DEVELOPMENT_TEAM=$TEAM_ID
          xcodebuild -exportArchive -archivePath build/WordAssistant.xcarchive \
            -exportOptionsPlist export-options.plist -exportPath build/export CODE_SIGNING_ALLOWED=YES
        env: { TEAM_ID: ${{ secrets.TEAM_ID }} }
      - uses: actions/upload-artifact@v4
        with: { name: WordAssistant-signed-ipa, path: ios-app/build/export/*.ipa }
```

`ios-app/export-options.plist`（按分发方式选择）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key><string>development</string>
    <key>signingStyle</key><string>manual</string>
</dict>
</plist>
```

---

## 本地构建（有 Mac + Xcode 时）

```bash
bash ios-app/scripts/fetch-db.sh          # 准备词典
brew install xcodegen
cd ios-app && xcodegen generate
xcodebuild archive -project WordAssistant.xcodeproj -scheme WordAssistant \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath build/WordAssistant.xcarchive CODE_SIGNING_ALLOWED=NO
```

---

## 数据迁移（换机/从 Android 版）

应用内「设置 → 导出数据」生成 JSON 备份，导入即可（词本、列表、设置、经验值）。

---

## 与 Android 版的差异

| 能力 | Android | iOS |
|---|---|---|
| 后端 | Python Flask (Chaquopy) | Swift 全量移植 |
| 发音 | Android TTS | AVSpeechSynthesizer + 在线有道发音 |
| 每日提醒 | AlarmManager + 通知 | 本地通知（UNUserNotificationCenter） |
| 导入导出 | SAF 文件选择器 | UIDocumentPicker |
| 状态栏/深色模式 | JS 桥 | JS 桥（模拟 window.Android） |

## 已知限制

- 未签名 IPA 需自签安装（7 天有效）；
- 完整词典首次启动需约 1 分钟初始化；
- 在线发音（有道）需网络，离线自动回退系统 TTS（iOS 需在设置中开启发音）。
