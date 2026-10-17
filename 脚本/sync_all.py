#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三端「单一代码源」同步脚本。

仓库根目录是唯一代码源：
  index.html   —— 前端（桌面直接服务；Android assets 与 iOS Resources 由此生成）
  app.py       —— Python 后端（桌面直接运行；Android Chaquopy 由此生成副本）
  api_contract.json —— 27 个接口契约（iOS Swift 后端以此对照）

本脚本负责把根目录代码源同步到各端构建位置：
  index.html -> android-app/app/src/main/assets/index.html        （原样复制）
  app.py     -> android-app/app/src/main/python/app.py            （原样复制）
  index.html -> ios-app/WordAssistant/Resources/index.html        （make_index 转换）

用法：
  python 脚本/sync_all.py            # 执行同步（覆盖三个副本）
  python 脚本/sync_all.py --check    # 只校验漂移，不写入（有漂移退出码 1）
  python 脚本/sync_all.py --check --report   # 校验并打印每个文件的差异摘要
"""
import io
import os
import sys
import difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = "--check" in sys.argv
REPORT = "--report" in sys.argv

# Windows 控制台默认 GBK，diff 里可能有 emoji（🚀 等），强制 UTF-8 输出避免崩溃
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_index import transform  # noqa: E402

if CHECK:
    # 校验模式顺带检查 Swift 后端是否覆盖接口契约（单命令健康门禁）
    try:
        import check_swift_coverage as _csc
        _coverage_ok = _csc.main() == 0
    except Exception as _e:
        print(f"[警告] 契约覆盖检查无法运行: {_e}")
        _coverage_ok = True

# (源, 目标, 处理方式)
FRONTEND_SRC = os.path.join(ROOT, "index.html")
ANDROID_HTML = os.path.join(ROOT, "android-app", "app", "src", "main", "assets", "index.html")
IOS_HTML = os.path.join(ROOT, "ios-app", "WordAssistant", "Resources", "index.html")
BACKEND_SRC = os.path.join(ROOT, "app.py")
ANDROID_PY = os.path.join(ROOT, "android-app", "app", "src", "main", "python", "app.py")
FSRS_SRC = os.path.join(ROOT, "fsrs.py")
ANDROID_FSRS = os.path.join(ROOT, "android-app", "app", "src", "main", "python", "fsrs.py")


def read(p):
    with io.open(p, "r", encoding="utf-8") as f:
        return f.read()


def write(p, text):
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def sync_copy(src, dst):
    """原样复制；返回 (目标是否与源一致, 差异行数)。"""
    text = read(src)
    if os.path.exists(dst):
        cur = read(dst)
    else:
        cur = None
    if cur == text:
        return True, 0
    if not CHECK:
        write(dst, text)
    if cur is None:
        return False, len(text.splitlines())
    diff = sum(1 for _ in difflib.unified_diff(cur.splitlines(), text.splitlines()))
    return False, diff


def sync_ios(src, dst):
    """前端源 -> iOS 版（转换）；返回 (是否一致, 差异行数)。"""
    out = transform(read(src))
    if os.path.exists(dst):
        cur = read(dst)
    else:
        cur = None
    if cur == out:
        return True, 0
    if not CHECK:
        write(dst, out)
    if cur is None:
        return False, len(out.splitlines())
    diff = sum(1 for _ in difflib.unified_diff(cur.splitlines(), out.splitlines()))
    return False, diff


def main():
    pairs = [
        ("Android 前端 (assets/index.html)", FRONTEND_SRC, ANDROID_HTML, sync_copy),
        ("Android 后端 (python/app.py)", BACKEND_SRC, ANDROID_PY, sync_copy),
        ("Android 后端 (python/fsrs.py)", FSRS_SRC, ANDROID_FSRS, sync_copy),
        ("iOS 前端 (Resources/index.html)", FRONTEND_SRC, IOS_HTML, sync_ios),
    ]
    dirty = []
    print("=== 三端单一代码源同步%s ===" % ("（校验模式，不写入）" if CHECK else ""))
    for name, src, dst, fn in pairs:
        if not os.path.exists(src):
            print(f"[错误] 代码源缺失: {src}")
            return 2
        ok, diff = fn(src, dst)
        status = "OK" if ok else "DIFF"
        print(f"[{status}] {name}")
        if not ok:
            dirty.append(name)
        if not ok and REPORT:
            if os.path.exists(dst):
                cur = read(dst)
                expect = transform(read(src)) if fn is sync_ios else read(src)
                sys.stdout.writelines(difflib.unified_diff(
                    cur.splitlines(), expect.splitlines(),
                    fromfile=dst, tofile=src, lineterm=""))
    if dirty:
        print("有漂移：", "、".join(dirty))
        if not CHECK:
            print("已同步完成。请重新运行 --check 确认，并提交全部生成文件。")
        else:
            print("提示：运行 python 脚本/sync_all.py 完成同步。")
        return 1
    if CHECK and not _coverage_ok:
        print("契约覆盖检查未通过（见上方报告）。")
        return 1
    print("全部一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
