#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 iOS Swift 后端与 Python 后端是否覆盖 api_contract.json 的全部接口。

用法：
  python scripts/check_swift_coverage.py          # 校验并报告（有缺口退出码 1）
  python scripts/check_swift_coverage.py --strict # 严格模式：responseKeys 也要求 Python 侧存在

原理（启发式，用于抓「漏实现/漂移」）：
  - Python 侧：解析 app.py 的 @app.route 装饰器，按 method+path 与契约逐条比对；
  - Swift 侧：读取 Api.swift 的 route() 函数，检查每个接口的「常量路径段」是否都在其 method 分支中被引用。
路径参数（{word}、{list_id} 等）没有常量段，只比对常量段；因此无法 100% 证明语义等价，
但任何「新增接口漏移植 / 路径段改名」都会在这里被抓住。
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACT = os.path.join(ROOT, "api_contract.json")
APP_PY = os.path.join(ROOT, "app.py")
API_SWIFT = os.path.join(ROOT, "ios-app", "WordAssistant", "Api.swift")

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def load_contract():
    with io.open(CONTRACT, "r", encoding="utf-8") as f:
        return json.load(f)["endpoints"]


def constant_segments(path):
    """去掉参数段后剩下的常量路径段，如 /api/wordbook/{word}/clear_wrong -> [api, wordbook, clear_wrong]。
    契约用 {name} 表示参数；Flask 路由用 <int:name>，Swift 用 comps 下标；都视为参数。"""
    return [s for s in path.strip("/").split("/")
            if not (s.startswith("{") and s.endswith("}")) and not (s.startswith("<") and s.endswith(">"))]


def parse_python_routes(text):
    """从 app.py 提取 {method: set(路径常量段元组)}。"""
    routes = {}
    for m in re.finditer(r"@app\.route\('([^']+)'(?:,\s*methods=\[([^\]]*)\])?\)", text):
        path = m.group(1)
        methods = re.findall(r"'(\w+)'", m.group(2) or "") or ["GET"]
        for method in methods:
            routes.setdefault(method, set()).add(tuple(constant_segments(path)))
    return routes


def extract_swift_route_body(text):
    """提取 Api.swift 中 route() 函数体（用于限定检索范围）。"""
    start = text.index("static func route")
    end = text.index("// MARK: - 工具", start)
    return text[start:end]


def check_python(endpoints, py_routes):
    problems = []
    for ep in endpoints:
        segs = tuple(constant_segments(ep["path"]))
        if segs not in py_routes.get(ep["method"], set()):
            problems.append(f"Python app.py 缺少 {ep['method']} {ep['path']}")
    return problems


def check_swift(endpoints, swift_body):
    problems = []
    for ep in endpoints:
        segs = constant_segments(ep["path"])
        for seg in segs:
            if seg == "api":
                continue  # 每个分支都有
            if f'"{seg}"' not in swift_body:
                problems.append(f"Swift Api.swift 未覆盖 {ep['method']} {ep['path']}（缺常量段 {seg}）")
                break
    return problems


def main():
    strict = "--strict" in sys.argv
    endpoints = load_contract()
    with io.open(APP_PY, "r", encoding="utf-8") as f:
        app_py = f.read()
    with io.open(API_SWIFT, "r", encoding="utf-8") as f:
        api_swift = f.read()

    py_problems = check_python(endpoints, parse_python_routes(app_py))
    swift_problems = check_swift(endpoints, extract_swift_route_body(api_swift))

    print(f"契约接口总数: {len(endpoints)}")
    print(f"Python 侧缺口: {len(py_problems)}")
    for p in py_problems:
        print("  [PY]", p)
    print(f"Swift 侧缺口: {len(swift_problems)}")
    for p in swift_problems:
        print("  [SWIFT]", p)

    # Python 响应键抽查（strict 模式）：GET 契约声明了 keys 的，在 app.py 里应有对应 jsonify 键
    if strict:
        py_missing = []
        for ep in endpoints:
            if ep["method"] != "GET":
                continue
            for key in ep.get("responseKeys", []):
                k = key.split("?")[0]
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
                    continue  # 占位符（如 <date>:{...}）跳过
                if f"'{k}'" not in app_py and f'"{k}"' not in app_py:
                    py_missing.append(f"{ep['method']} {ep['path']} 缺响应键 {k}")
        print(f"Python 响应键缺口（strict）: {len(py_missing)}")
        for p in py_missing:
            print("  [PY-STRICT]", p)
        py_problems += py_missing

    if py_problems or swift_problems:
        print("结果: 存在缺口，请补齐后重跑。")
        return 1
    print("结果: Python 与 Swift 均已覆盖全部契约接口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
