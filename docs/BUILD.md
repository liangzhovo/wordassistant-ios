# 🛠 单词助手 · 构建操作手册

> 本文件是**触发构建 / 观看进度 / 下载安装**的快速指南。仓库已整理为「单一代码源」：
> 改根目录 `index.html` / `app.py` / `api_contract.json` → `python scripts\sync_all.py` → 提交 → 三端构建。

## 总览

```
桌面版（Windows 本机）      python app.py / 启动.bat     —— 即手机端行为基线
Android APK（本机构建）     一键构建APK.bat             —— 双击即构建
iOS IPA（云端 CI 构建）      python build.py            —— 触发 / 观看 / 下载
```

## 一键构建控制台（推荐入口）

根目录运行（Windows 双击 `启动.bat` 之外的统一入口）：

```bat
python build.py
```

菜单：
1. **触发 iOS 构建** —— `gh workflow run build-ipa.yml`，云端编译未签名 IPA
2. **观看最新构建进度** —— 实时滚动日志，结束后显示结果与链接
3. **下载最新 IPA 到 dist/** —— 从 Release `ipa-latest` 下载
4. **查看 Release 状态** —— 词典 `data-v1`（应为 103 MB 级 v2）与最新 IPA
5. **打开 GitHub Actions 网页** —— 浏览器查看日志/产物
6. **三端同步 + 契约检查** —— `scripts/sync_all.py --check`（含 Swift 27 接口覆盖）
7. **桌面接口冒烟测试** —— `scripts/smoke_api.py`（29 项，词典临时副本）
8. **构建 Android APK（新窗口）** —— 运行 `一键构建APK.bat`
9. **启动桌面版**

也可带参数直接执行单步：`python build.py 1`（触发）、`python build.py 2`（观看）。

## iOS IPA（云端构建）

| 操作 | 命令 / 位置 |
|---|---|
| 触发 | `python build.py 1`，或网页 https://github.com/liangzhovo/wordassistant-ios/actions → Run workflow |
| 观看 | `python build.py 2`（实时）；网页 Actions 页最直观 |
| 下载 | `python build.py 3`，或 Release 页 https://github.com/liangzhovo/wordassistant-ios/releases/tag/ipa-latest |
| 安装 | 爱思助手 / Sideloadly / AltStore 用 Apple ID 自签（7 天有效） |

触发条件：推送命中 `index.html` / `app.py` / `scripts/**` / `api_contract.json` / `ios-app/**` /
工作流文件即自动构建；也可网页手动 Run workflow。

## Android APK（本机构建）

双击 `android-app/一键构建APK.bat`，可选参数：

```bat
一键构建APK.bat            :: release 正式签名版（默认）
一键构建APK.bat debug      :: debug 版
一键构建APK.bat install    :: 构建后自动 adb 安装到已连接手机
一键构建APK.bat check      :: 只检查 JDK/SDK 环境，不构建
```

- 构建前自动执行三端同步（`scripts/sync_all.py`），改根目录代码直接生效；
- APK 输出：`android-app\app\build\outputs\apk\release\app-release.apk`（或 debug）；
- 需要本机 JDK 17 + Android SDK（`android-app/local.properties` 已配置 sdk.dir）。

## 桌面版（Windows 测试 = 手机端）

```bat
启动.bat        :: python app.py，弹出 450x800 手机比例窗口
python scripts\smoke_api.py   :: 29 项接口冒烟（词典临时副本，不动原库）
```

## 构建前必做（纪律）

1. 只改根目录三个源文件（`index.html` / `app.py` / `api_contract.json`）；
2. `python scripts\sync_all.py`（生成 Android / iOS 副本）；
3. 提交**全部**生成文件（CI 构建前也会校验，未同步会失败）。

## 相关文档

| 文件 | 内容 |
|---|---|
| `docs/README.md` | 项目全貌 + 单一代码源章节 |
| `docs/GIT_WORKFLOW.md` | 提交/推送/Release/踩坑速查 |
| `ios-app/BUILD_HANDOFF.md` | iOS 构建交接细节与验证清单 |
| `archive/` | 已废弃的历史脚本与文档（勿用） |
