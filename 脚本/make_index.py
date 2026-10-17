# -*- coding: utf-8 -*-
"""从仓库根目录 index.html（唯一前端源）生成 iOS 版 index.html：
1) apiPost 的 body 改走 query 参数（WKURLSchemeHandler 收不到 POST body）
2) fmtTrans 去掉 lookbehind 正则（iOS 15/16 引擎不支持）

本文件同时被 脚本/sync_all.py 复用（transform 函数），也可单独运行：
  python 脚本/make_index.py            # 读取根 index.html，写入 ios Resources
  python 脚本/make_index.py --check    # 只校验转换结果是否与现有 iOS 文件一致
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "index.html")
DST = os.path.join(ROOT, "ios-app", "WordAssistant", "Resources", "index.html")

_OLD_POST = "const res = await fetch(apiUrl + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });"
_NEW_POST = ("const sep = path.indexOf('?') >= 0 ? '&' : '?'; "
             "const res = await fetch(apiUrl + path + sep + '_body=' + encodeURIComponent(JSON.stringify(data)), { method: 'POST' });")

_OLD_FMT = "function fmtTrans(t) { return (t || '').replace(/(?<=\\s|^)a\\./g, 'adj.'); }"
_NEW_FMT = "function fmtTrans(t) { return (t || '').replace(/(^|\\s)a\\./g, '$1adj.'); }"


def transform(html: str) -> str:
    """把通用前端转换为 iOS 版（body 走 query、去 lookbehind）。"""
    n = html.count(_OLD_POST)
    assert n == 1, f"apiPost 模式匹配到 {n} 次（预期 1 次），请检查前端源是否变化"
    html = html.replace(_OLD_POST, _NEW_POST)

    n = html.count(_OLD_FMT)
    assert n == 1, f"fmtTrans 模式匹配到 {n} 次（预期 1 次），请检查前端源是否变化"
    html = html.replace(_OLD_FMT, _NEW_FMT)
    return html


def main():
    with io.open(SRC, "r", encoding="utf-8") as f:
        html = f.read()
    out = transform(html)

    if "--check" in sys.argv:
        with io.open(DST, "r", encoding="utf-8") as f:
            cur = f.read()
        if cur == out:
            print("OK: iOS 版 index.html 与根目录源一致（无漂移）")
            return 0
        print("DIFF: iOS 版 index.html 过期，需重新生成（运行 脚本/sync_all.py）")
        return 1

    with io.open(DST, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("written", len(out), "bytes ->", DST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
