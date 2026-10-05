# 🦉 单词助手 · iOS 构建交接说明（ECDICT 学生版词库）

> **给负责构建 iOS 的 AI / 开发者**
> 本文档说明：词典数据源已更换，iOS 构建前需要**上传哪些文件**、**按什么顺序构建**、**如何验证**。
> 请先通读，再执行构建。

---

## 1. 本次变更：词典数据源更换

| 项目 | 旧（已废弃） | 新（当前） |
|---|---|---|
| 数据源 | 简明英汉字典增强版（MDX 转换版，332 万词条） | **ECDICT**（76 万词条，含中考/高考/牛津三千标签、BNC/当代词频、词形变化） |
| 释义格式 | MDX 标记（`` `1` ``、`</br>`、`[计]` 学科标签、冷门义项在前） | **干净格式**：`[音标] 词性. 释义`（每行一个词性组，首行为最常用义项） |
| 典型查询结果 | `good → n. 善行, 好处, 利益`（冷门） | `good → adj. 好的`（学生友好） |
| 词条覆盖 | 332 万（含大量地名/人名/领域术语） | 约 76 万 + 词形变化展开（学习场景完全覆盖） |

**文件名保持不变**（`简明英汉字典增强版.db` / `.db.small`），**只是内容换源**。因此 iOS 代码（`Database.swift` 的 bootstrap、`SchemeHandler.swift` 的 API 路由）**不需要改动**，仅 `Utils.swift` 的释义清洗逻辑已同步适配新格式（`ios-app/WordAssistant/Utils.swift` 已更新）。

---

## 2. 词典文件（构建前必须就位）

三端共用一份数据，位置在：

| 文件 | 内容 | 用途 | 是否入库 |
|---|---|---|---|
| `android-app/app/src/main/assets/简明英汉字典增强版.db` | **ECDICT 全量：301,182 词条（23.9 万原词 + 6.2 万词形变化变体），43.5 MB** | iOS 主词典 / 桌面 / Android | ❌ 太大，由 Release 提供 |
| `android-app/app/src/main/assets/简明英汉字典增强版.db.small` | **学生核心：3,541 词条（中考 zk + 牛津三千 oxford），0.7 MB** | CI 回退 / Android 精简 | ✅ 随仓库提交 |

> 均由仓库根目录 `build_ecdict_dict.py` 从 `ecdict.csv` 构建（释义按"常见词性优先 + 义项数启发"排好序）。

---

## 3. 上传要求（重要）

`ios-app/scripts/fetch-db.sh` 的优先级不变：
**本地 assets 已有完整版 → 直接从 GitHub Release 下载 → 回退精简库（.small）**。

因此构建前二选一：

- **方式 A（CI / GitHub Actions）**：先把新完整版上传到 Release，再触发工作流：
  ```bash
  gh release upload data-v1 "android-app/app/src/main/assets/简明英汉字典增强版.db" --clobber
  ```
  或直接运行仓库根目录的现成脚本：`node upload-db.js`（自动取 git 凭据、建 release、上传）。
  CI 的 `fetch-db.sh` 会自动下载。若未上传，CI 将自动回退到精简库（功能一致，仅覆盖核心词）。

- **方式 B（本地 Mac）**：确保上面 `assets/简明英汉字典增强版.db` 已存在（本地下载/拷贝），直接：
  ```bash
  bash ios-app/scripts/fetch-db.sh        # 会使用本地完整版
  brew install xcodegen
  cd ios-app && xcodegen generate
  ```

---

## 4. 构建命令（不变）

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

产出 `WordAssistant-unsigned.ipa`（未签名），打包方式见 `.github/workflows/build-ipa.yml`。

---

## 5. 验证清单

构建完成后请逐项确认：

1. **archive 成功**，`WordAssistant.app` 存在，IPA 打包成功；
2. **词典文件就位**：`WordAssistant.app/简明英汉字典增强版.db` 存在且非 0 字节（构建日志可查 `ls -lh`）；
3. **模拟器/真机启动**：首次启动会复制词典并建索引（新库小，初始化明显更快）；
4. **释义展示**：搜索 `good`、`run`、`about`、`apple`——
   - 音标正常（如 `good → [gud]`）；
   - 释义为首个常用义项（如 `good → adj. 好的`，不再出现 `n. 善行` 之类冷门义项）；
   - 无 MDX 标记（无 `` `1` ``、`</br>`、`[计]` 残留）；
5. **词形变化**：查 `ran`、`running`、`took` 等变体词能命中（完整版已展开变体）；
6. **功能回归**：生词本添加、SM-2 复习、错题本、打卡、导出导入、每日提醒均正常。

---

## 6. 注意事项

- 完整版词典（约百余 MB）**不要直接 push 到仓库**（超 GitHub 仓库大小限制），走 Release（`data-v1`）；
- `.db.small`（学生核心，几 MB）**已随仓库提交**，push 时正常携带；
- 若 `Utils.swift` / `Api.swift` 与 `app.py` 行为出现偏差，以 `app.py`（桌面/Android 共用后端）为准对齐；
- 前端 `ios-app/WordAssistant/Resources/index.html` 由 `ios-app/scripts/make_index.py` 从 `android-app/app/src/main/assets/index.html` 生成（POST body 走 query、去除 lookbehind），**每次前端改动后需重新生成并提交**。

---

## 7. 相关文件索引

| 文件 | 说明 |
|---|---|
| `build_ecdict_dict.py` | 从 `ecdict.csv` 构建完整版 + 精简版词典库（仓库根目录） |
| `ecdict.csv` | ECDICT 原始数据（63MB，不在仓库内，见 [ECDICT 仓库](https://github.com/skywind3000/ECDICT)） |
| `app.py` / `android-app/.../python/app.py` | 后端释义清洗已适配新格式 |
| `ios-app/WordAssistant/Utils.swift` | iOS 释义清洗已适配新格式 |
| `ios-app/scripts/fetch-db.sh` | 词典准备脚本（未改动） |
| `.github/workflows/build-ipa.yml` | CI 构建工作流（未改动） |
