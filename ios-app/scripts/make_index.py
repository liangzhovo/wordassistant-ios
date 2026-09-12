# -*- coding: utf-8 -*-
"""从 android 资产生成 iOS 版 index.html：
1) apiPost 的 body 改走 query 参数（WKURLSchemeHandler 收不到 POST body）
2) fmtTrans 去掉 lookbehind 正则（iOS 15/16 引擎不支持）
"""
import io

SRC = r"E:\app\单词助手\android-app\app\src\main\assets\index.html"
DST = r"E:\app\单词助手\ios-app\WordAssistant\Resources\index.html"

with io.open(SRC, "r", encoding="utf-8") as f:
    html = f.read()

old_post = "const res = await fetch(apiUrl + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });"
new_post = ("const sep = path.indexOf('?') >= 0 ? '&' : '?'; "
            "const res = await fetch(apiUrl + path + sep + '_body=' + encodeURIComponent(JSON.stringify(data)), { method: 'POST' });")
n = html.count(old_post)
assert n == 1, f"apiPost pattern found {n} times"
html = html.replace(old_post, new_post)

old_fmt = "function fmtTrans(t) { return (t || '').replace(/(?<=\\s|^)a\\./g, 'adj.'); }"
new_fmt = "function fmtTrans(t) { return (t || '').replace(/(^|\\s)a\\./g, '$1adj.'); }"
n = html.count(old_fmt)
assert n == 1, f"fmtTrans pattern found {n} times"
html = html.replace(old_fmt, new_fmt)

with io.open(DST, "w", encoding="utf-8", newline="\n") as f:
    f.write(html)
print("written", len(html), "bytes ->", DST)
