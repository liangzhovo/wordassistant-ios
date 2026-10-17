#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单词助手 · 构建控制台（Windows 一键触发 / 观看 / 下载构建）

用法：
  python build.py            # 交互式菜单
  python build.py 1          # 直接执行菜单第 1 项（触发 iOS CI 构建）
  python build.py 2          # 直接执行菜单第 2 项（观看最新构建进度）

依赖：gh CLI 已登录（首次运行会自动检查）。

菜单：
  1. 触发 iOS 构建（GitHub Actions 云端构建 IPA）
  2. 观看最新构建进度（实时滚动，结束后显示结果与链接）
  3. 下载最新 IPA 到 dist/
  4. 查看 Release 状态（data-v1 词典 / ipa-latest）
  5. 打开 GitHub Actions 网页
  6. 三端同步 + 契约检查（脚本/sync_all.py）
  7. 桌面接口冒烟测试（脚本/smoke_api.py，29 项）
  8. 构建 Android APK（新窗口运行 一键构建APK.bat）
  9. 启动桌面版（python app.py）
"""
import os
import shutil
import subprocess
import sys

REPO = "liangzhovo/wordassistant-ios"
ROOT = os.path.dirname(os.path.abspath(__file__))
WORKFLOW = "build-ipa.yml"

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _env_with_proxy():
    """本机 xray 代理（127.0.0.1:10808）可用时，给 gh 挂上代理（直连 GitHub 下载很慢）。"""
    env = dict(os.environ)
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect(("127.0.0.1", 10808))
        env["HTTP_PROXY"] = "http://127.0.0.1:10808"
        env["HTTPS_PROXY"] = "http://127.0.0.1:10808"
    except OSError:
        pass
    finally:
        s.close()
    return env


def run(cmd, stream=False, cwd=None, use_proxy=True):
    """执行命令；stream=True 时实时透传输出（用于观看构建）。
    一律字节模式读取后手动 UTF-8 解码（errors=replace），避免 Windows GBK 控制台解码崩溃。"""
    print("$", " ".join(cmd))
    kwargs = dict(cwd=cwd or ROOT, env=_env_with_proxy() if use_proxy else None)
    if stream:
        return subprocess.run(cmd, **kwargs).returncode
    p = subprocess.run(cmd, capture_output=True, **kwargs)
    if p.stdout:
        print(p.stdout.decode("utf-8", errors="replace").rstrip())
    if p.stderr:
        print(p.stderr.decode("utf-8", errors="replace").rstrip(), file=sys.stderr)
    return p.returncode


def gh_json(args):
    """执行 gh <args> --json <fields>，返回解析后的 JSON（纯 Python，不经 jq）。"""
    p = subprocess.run(["gh"] + args, capture_output=True, env=_env_with_proxy())
    if p.returncode != 0:
        print(p.stderr.decode("utf-8", errors="replace").rstrip(), file=sys.stderr)
        return None
    try:
        import json
        return json.loads(p.stdout.decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"[错误] 解析 gh 输出失败: {e}", file=sys.stderr)
        return None


def gh_ok():
    p = subprocess.run(["gh", "auth", "status"], capture_output=True)
    if p.returncode != 0:
        print(p.stderr.decode("utf-8", errors="replace").rstrip(), file=sys.stderr)
        print("[错误] gh CLI 未登录。请先运行: gh auth login")
        return False
    return True


def latest_run_id():
    data = gh_json(["run", "list", "--repo", REPO, "--workflow", WORKFLOW, "--limit", "1",
                    "--json", "databaseId"])
    if data and isinstance(data, list) and data:
        return str(data[0].get("databaseId", ""))
    return None


def action_trigger():
    """触发 iOS CI 构建。"""
    print("触发构建：GitHub Actions 云端编译 iOS IPA（未签名，约 1~3 分钟）...")
    rc = run(["gh", "workflow", "run", WORKFLOW, "--repo", REPO, "--ref", "main"])
    if rc != 0:
        print("[失败] 触发失败，请检查网络（直连慢时走代理）或 gh 登录。")
        return 1
    print("[OK] 已触发。建议立即执行菜单 2 观看进度。")
    return 0


def action_watch():
    """观看最新构建进度。"""
    run_id = latest_run_id()
    if not run_id:
        print("[错误] 未找到构建记录（可能从未触发过）。")
        return 1
    print(f"观看构建 #{run_id} ...（Ctrl+C 可中断观看，不影响云端构建）")
    rc = run(["gh", "run", "watch", run_id, "--repo", REPO, "--exit-status", "--interval", "10"], stream=True)
    print("-" * 50)
    run(["gh", "run", "view", run_id, "--repo", REPO])
    if rc == 0:
        print("[OK] 构建成功。菜单 3 下载 IPA。")
    else:
        print("[失败] 构建未成功，见上方日志或打开菜单 5 查看网页版详情。")
    return rc


def action_download():
    """下载最新 IPA 到 dist/。"""
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    print("下载 ipa-latest 到 dist/ ...")
    rc = run(["gh", "release", "download", "ipa-latest", "--repo", REPO,
              "--pattern", "WordAssistant-unsigned.ipa", "--dir", dist, "--clobber"])
    if rc != 0:
        print("[失败] 下载失败（Release 可能还没有产物）。")
        return 1
    for name in os.listdir(dist):
        p = os.path.join(dist, name)
        if os.path.isfile(p):
            print(f"[OK] {name}  {os.path.getsize(p) / 1024 / 1024:.1f} MB -> dist\\{name}")
    print("安装方法：爱思助手 / Sideloadly / AltStore 自签安装。")
    return 0


def action_status():
    """查看 Release 状态。"""
    def fmt_assets(release):
        data = gh_json(["release", "view", release, "--repo", REPO, "--json", "assets"])
        if not data:
            return
        for a in data.get("assets", []):
            print(f"  {a['name']}  {a['size'] / 1024 / 1024:.1f} MB")
    print("=== data-v1（词典，应为 103 MB 级 = v2 完整版） ===")
    fmt_assets("data-v1")
    print("=== ipa-latest（最新 IPA） ===")
    fmt_assets("ipa-latest")
    return 0


def action_open_web():
    """打开 GitHub Actions 网页。"""
    url = f"https://github.com/{REPO}/actions"
    print(f"打开 {url}")
    if sys.platform.startswith("win"):
        os.startfile(url)  # noqa: S606
    else:
        run(["open", url])
    return 0


def action_sync():
    """三端同步 + 契约检查。"""
    return run([sys.executable, os.path.join("脚本", "sync_all.py"), "--check"])


def action_smoke():
    """桌面接口冒烟测试。"""
    return run([sys.executable, os.path.join("脚本", "smoke_api.py")])


def action_android():
    """新窗口运行一键构建APK.bat。"""
    bat = os.path.join(ROOT, "android-app", "一键构建APK.bat")
    print(f"打开构建窗口: {bat}")
    subprocess.Popen(["cmd", "/c", "start", "", bat], cwd=ROOT)
    return 0


def action_desktop():
    """启动桌面版。"""
    print("启动桌面版（新窗口: python app.py）")
    subprocess.Popen(["cmd", "/c", "start", "", "启动.bat"], cwd=ROOT)
    return 0


MENU = [
    ("触发 iOS 构建", action_trigger),
    ("观看最新构建进度", action_watch),
    ("下载最新 IPA 到 dist/", action_download),
    ("查看 Release 状态", action_status),
    ("打开 GitHub Actions 网页", action_open_web),
    ("三端同步 + 契约检查", action_sync),
    ("桌面接口冒烟测试", action_smoke),
    ("构建 Android APK（新窗口）", action_android),
    ("启动桌面版", action_desktop),
]


def main():
    if not gh_ok():
        return 1
    if len(sys.argv) > 1:
        try:
            idx = int(sys.argv[1])
        except ValueError:
            print("用法: python build.py [1-9]")
            return 2
        if 1 <= idx <= len(MENU):
            return MENU[idx - 1][1]()
        print("无效菜单编号。")
        return 2
    while True:
        print()
        print("=" * 52)
        print("  单词助手 · 构建控制台（iOS CI / Android 本地 / 桌面）")
        print("=" * 52)
        for i, (label, _) in enumerate(MENU, 1):
            print(f"  {i}. {label}")
        print("  0. 退出")
        try:
            choice = input("\n请输入编号: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if choice == "0":
            break
        if choice.isdigit() and 1 <= int(choice) <= len(MENU):
            MENU[int(choice) - 1][1]()
        else:
            print("无效输入，请输入 0~9。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
