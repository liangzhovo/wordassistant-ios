#!/usr/bin/env bash
# 准备 iOS 构建用词典：
#   1) 若 android-app 资产中已有完整词典 -> 直接使用
#   2) 否则尝试从 GitHub Release (data-v1) 下载 488MB 完整版
#   3) 都失败则回退到仓库内的 82MB 精简库（功能一致，词条 98 万）
# 用法: bash ios-app/scripts/fetch-db.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TARGET="$REPO_ROOT/android-app/app/src/main/assets/简明英汉字典增强版.db"

if [ -s "$TARGET" ]; then
  echo "[fetch-db] 词典已存在: $TARGET"
  ls -lh "$TARGET"
  exit 0
fi

mkdir -p "$(dirname "$TARGET")"

if [ -n "${GITHUB_REPOSITORY:-}" ] && command -v gh >/dev/null 2>&1; then
  echo "[fetch-db] 尝试从 GitHub Release 下载完整词典..."
  if gh release download "data-v1" \
      --pattern "简明英汉字典增强版.db" \
      --repo "$GITHUB_REPOSITORY" \
      --dir "$(dirname "$TARGET")" 2>/dev/null; then
    echo "[fetch-db] 完整词典下载成功"
    ls -lh "$TARGET"
    exit 0
  fi
  echo "[fetch-db] Release 下载失败，回退精简库"
else
  echo "[fetch-db] 未在 CI 环境或 gh 不可用，回退精简库"
fi

SMALL="$REPO_ROOT/android-app/app/src/main/assets/简明英汉字典增强版.db.small"
if [ -s "$SMALL" ]; then
  cp "$SMALL" "$TARGET"
  echo "[fetch-db] 已使用精简库 (98 万词条)"
else
  echo "[fetch-db] 错误: 找不到任何词典文件" >&2
  exit 1
fi
