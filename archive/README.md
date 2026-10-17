# archive · 历史脚本与文档（已归档）

这里存放**已废弃**的构建脚本与文档，仅供查阅历史，**不要使用**。

## 脚本

| 文件 | 废弃原因 |
|---|---|
| `build_apk.bat` | 早期 Gradle 构建脚本，无三端同步、无环境检测，被 `一键构建APK.bat` 取代 |
| `build_final.bat` / `build_manual.bat` / `build_simple.bat` | **占位脚本**，生成的是假 APK 文本文件，会误导构建 |
| `BUILD_PYTHON_APK.bat` | 早期 Chaquopy 构建脚本，被 `一键构建APK.bat` 取代 |

## 文档

| 文件 | 废弃原因 |
|---|---|
| `README.md` / `BUILD_INSTRUCTIONS.md` / `BUILD_INSTRUCTIONS_ANDROID_STUDIO.md` | 旧架构（NanoHTTPD/8080 端口）说明，当前架构为 Chaquopy + Flask（5000 端口） |
| `BUILD_INSTRUCTIONS_PYTHON.md` / `README_PYTHON.md` | 早期 Chaquopy 文档，已由 `docs/README.md`（单一代码源章节）与 `docs/BUILD.md`（构建操作手册）取代 |

## 当前唯一构建入口

- **Android APK**：双击 `android-app/一键构建APK.bat`
- **iOS IPA（CI）**：`python build.py`（构建控制台，可触发/观看/下载）
- **桌面版**：`启动.bat`（`python app.py`）

详见 [docs/BUILD.md](../docs/BUILD.md)。
