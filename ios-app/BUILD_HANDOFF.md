# 🦉 单词助手 · iOS 构建交接说明（ECDICT 学生版词库 · v2 修复版）

> **给负责构建 iOS 的 AI / 开发者**
> 本文档说明：词典数据源已更换为 **ECDICT 学生版 v2 修复版**，iOS 构建前需要**上传哪些文件**、**按什么顺序构建**、**如何验证**。
> ⚠️ **请先通读第 1、3 节**——v2 修复了一个会导致「搜不到单词」的构建 bug，**必须使用 v2 词典重新上传与构建**，不要沿用之前上传的旧版词典。

---

## 1. ⚠️ 重要：本次词典必须是 v2 修复版

上一版（v1：43.5 MB / 301,182 词条）存在**构建期 bug**：

- 所有「**无音标的单行释义**」词条被误丢弃 → 大量**词组**（`a few`、`get up`、`look after`、`according to`）和常用词（`laptop`、`website`、`importantly`）**搜不到**（搜索提示"没有这个单词"）；
- **变体词条覆盖原词**（`went` 曾显示 `go` 的音标/释义）。

**v2 已修复（当前工作区即为 v2）**：

| 指标 | v1（废弃） | **v2（当前）** |
|---|---|---|
| 完整版词条数 | 301,182 | **768,999**（77 万，重复 0）|
| 完整版大小 | 43.5 MB | **103.27 MB** |
| 教材词汇覆盖 | 465 / 472 | **472 / 472**（含 `upcycle` 等 ECDICT 未收录词，已用教材 JSON 兜底）|
| 词组（a few / get up …）| ❌ 搜不到 | ✅ 可查 |
| 词形变化 | went → go 的音标（错误）| ✅ `went → [went] go的过去式` |
| 释义质量 | `good → adj. 好的` 等已优化 | 保持（常见词性优先 + 义项数启发）|

**一句话：如果 Release `data-v1` 里存的是旧版完整词典，必须用 v2 覆盖，否则 iOS 上会出现"搜不到词组/部分单词"。**

---

## 2. 词典文件（构建前必须就位）

三端共用一份数据，位置为（**文件名不变，内容已换源**）：

| 文件 | 内容 | 用途 | 是否入库 |
|---|---|---|---|
| `android-app/app/src/main/assets/简明英汉字典增强版.db` | **ECDICT v2 完整版：768,999 词条 / 103.27 MB** | iOS 主词典 / 桌面 / Android | ❌ 太大，由 Release 提供 |
| `android-app/app/src/main/assets/简明英汉字典增强版.db.small` | **学生核心：3,758 词条（中考 zk + 牛津三千 + 教材兜底）/ 0.72 MB** | CI 回退 / Android 精简 | ✅ 随仓库提交 |

> 均由仓库根目录 `build_ecdict_dict.py` 从 `ecdict.csv` 构建（两遍法：原词优先插入、变体去重补充 + 教材词兜底）。

---

## 3. 上传要求（必须在构建前完成）

`ios-app/scripts/fetch-db.sh` 优先级不变：**本地 assets 已有完整版 → GitHub Release（data-v1）下载 → 回退精简库（.small）**。

因此构建前二选一：

- **方式 A（CI / GitHub Actions，推荐）**：把 v2 完整版上传到 Release **覆盖旧版**，再触发工作流：
  ```bash
  node upload-db.js
  # 等价于：
  # gh release upload data-v1 "android-app/app/src/main/assets/简明英汉字典增强版.db" --clobber
  ```
  ⚠️ **注意资产命名**：GitHub 会把中文文件名自动改成 `default.db`——这是正常现象，**不要改 asset 名字，也不要因此迷惑**；`ios-app/scripts/fetch-db.sh`（提交 `f04aea7`）已支持按 `*.db` 兜底下载并改名为目标文件名。
  上传后可用 `gh release view data-v1` 确认 asset 大小应为 **103 MB 级**（若是 43 MB 级则还是旧版，需重传）。
  若未上传，CI 将自动回退到精简库（功能一致，仅覆盖核心词与教材词）。

- **方式 B（本地 Mac）**：确保上面 `assets/简明英汉字典增强版.db` 已存在（下载 v2 或本地拷贝），直接：
  ```bash
  bash ios-app/scripts/fetch-db.sh        # 使用本地 v2 完整版
  brew install xcodegen
  cd ios-app && xcodegen generate
  ```

---

## 4. 代码与仓库状态（重要）

- **释义清洗已对齐**：`app.py`（桌面/Android 共用后端）与 `ios-app/WordAssistant/Utils.swift` 的 `cleanParaphrase` 已适配新格式（`[音标]词性. 释义`，首行最常用义项），已随提交 `99de2c7` 入库。
- **⚠️ iOS 搜索全 404 的根因已确诊（真机实测），修复在 `Database.swift`（工作区待提交），必须随下个 IPA 发布**：
  - **根因**：`bootstrap()` 里 `Bundle.main.url(forResource: "简明英汉字典增强版", withExtension: "db")` **对中文资源名的精确查找在真机上 miss**（词典明明在 bundle 里，大小 103.2MB 已验证）。`url(forResource:)` 返回 nil → 抛错「内置词典文件缺失」→ 被 viewDidLoad 的 `catch { print }` 静默吞掉 → **App Support 里只剩 SQLITE_OPEN_CREATE 建的空库**（无 `mdx` 表）→ 所有搜索/联想返回 404「没有这个单词哦」；
  - **诊断特征**（用户真机）：启动画面（紫色"正在初始化词典…"）**一闪而过**（拷贝未发生）；任意词（含 `apple`）搜不到；但底部导航仍可手动进入搜索页（boot 失败不阻断 UI）；
  - **修复 A（已写入工作区）**：查找兜底——精确名 miss 时用 `Bundle.main.urls(forResourcesWithExtension: "db", subdirectory: nil)` 枚举所有 `.db` 资源（排除 `.small`）取第一个，再拷贝；
  - **后备方案 B（若枚举仍 miss）**：打包阶段改用 **ASCII 文件名**（如 `dict.db`）——CI 在构建前把词典复制为 `ios-app/WordAssistant/Resources/dict.db`，`project.yml` 引用该 ASCII 资源，`Database.swift` 同步改名为 `dict.db`（彻底规避中文资源名问题）；
  - **发布后必须验证**：模拟器/真机安装 → 首次启动画面应**停留数秒~数十秒**（正在拷贝 103MB）→ 搜 `apple`/`good`/`a few` 均命中；已装旧 IPA 的用户需卸载重装（或新版本自动触发坏库重拷，`isValidDictionary(at:)` 已在工作区）。
- **请确认这两个文件已提交/推送**（当前工作区为最新 v2 版本）：
  - `android-app/app/src/main/assets/简明英汉字典增强版.db.small`（757,760 bytes）
  - `build_ecdict_dict.py`（两遍法 + 教材兜底）
- 若从全新 clone 构建：先 `git pull` 拿到上面文件（含 `Database.swift` 修复）→ 再执行第 3 节上传 → 构建。

---

## 5. 构建命令

```bash
cd ios-app
xcodegen generate
xcodebuild archive \
  -project WordAssistant.xcodeproj \
  -scheme WordAssistant \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath build/WordAssistant.xcarchive \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=""
```

产出 `WordAssistant-unsigned.ipa`（未签名），打包/上传流程见 `.github/workflows/build-ipa.yml`（含 IPA 上传到 GitHub Release `ipa-latest`）。

---

## 6. 验证清单

构建完成后请逐项确认（重点：⚠️ 带 **v2 专项** 标记的项是修复验证）：

1. **archive 成功**，`WordAssistant.app` 存在，IPA 打包成功；
2. **词典就位**：`WordAssistant.app/简明英汉字典增强版.db` 存在且大小 **≈103 MB**（若是 43 MB 则打包的是旧版）；
3. **模拟器/真机启动**：首次启动复制词典并建索引（103 MB 库初始化更快）；
4. **释义展示**：搜 `good` → `[gud] adj. 好的…`；`run` → `vi. 跑…`；`apple` → `n. 苹果, 家伙`；无 MDX 标记残留；
5. ⚠️ **v2 专项：词组可查**：搜 `a few`、`get up`、`look after`、`according to` 均能出结果（v1 会提示"没有这个单词"）；
6. ⚠️ **v2 专项：常见词完整**：搜 `laptop`、`website`、`importantly`、`role model`（如教材有）均能命中；
7. ⚠️ **v2 专项：变体音标正确**：搜 `went` → `[went] go的过去式`（音标是 went 自己的，不是 go 的）；`took` → `[tuk] take的过去式`；`ran` → `[ræn] run的过去式`；
8. ⚠️ **v2 专项：教材词全覆盖**：抽查 `upcycle`（教材 9 上词，ECDICT 未收录，由兜底补入）能命中；
9. **功能回归**：生词本添加、SM-2 复习、错题本、打卡、导出导入、每日提醒均正常。

---

## 7. 注意事项

- 完整版词典（103 MB）**不要直接 push 到仓库**（超 GitHub 仓库大小限制），走 Release（`data-v1`）；
- **data-v1 必须保留 v2 完整版资产**（GitHub 会存成名字 `default.db`，103.2 MB 即为 v2；`fetch-db.sh` 已兼容，无需改名）；不要删除或替换为旧版，否则 iOS 会回退精简版导致大量单词搜不到；
- `.db.small`（学生核心，0.72 MB）**随仓库提交**，push 时正常携带；
- **上传 data-v1 必须 `--clobber` 覆盖**（`node upload-db.js` 已内置），避免 CI 下载到旧 v1；
- 若 `Utils.swift` / `Api.swift` 与 `app.py` 行为出现偏差，以 `app.py` 为准对齐；
- 前端 `ios-app/WordAssistant/Resources/index.html` 由 `ios-app/scripts/make_index.py` 从 `android-app/app/src/main/assets/index.html` 生成（POST body 走 query、去除 lookbehind 正则），**每次前端改动后需重新生成并提交**；
- 词典由 `build_ecdict_dict.py` 从 `ecdict.csv`（ECDICT 原始数据，63 MB，见 [ECDICT 仓库](https://github.com/skywind3000/ECDICT)）可复现重建。

---

## 8. 相关文件索引

| 文件 | 说明 |
|---|---|
| `build_ecdict_dict.py` | 从 `ecdict.csv` 构建 v2 完整版 + 精简版（两遍法 + 教材兜底） |
| `upload-db.js` | 一键上传完整版到 GitHub Release `data-v1`（`--clobber` 覆盖） |
| `ecdict.csv` | ECDICT 原始数据（63 MB，不在仓库内） |
| `app.py` / `android-app/.../python/app.py` | 后端释义清洗，已对齐新格式（提交 `99de2c7`） |
| `ios-app/WordAssistant/Utils.swift` | iOS 释义清洗，已对齐新格式（提交 `99de2c7`） |
| `ios-app/scripts/fetch-db.sh` | 词典准备脚本（已更新，提交 `f04aea7`：支持 GitHub 把中文资产名改为 `default.db` 的情况，按 `*.db` 兜底下载并改名） |
| `.github/workflows/build-ipa.yml` | CI 构建 + IPA 上传 Release（含 IPA 打包修复） |