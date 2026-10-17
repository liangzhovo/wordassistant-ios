#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桌面端（Windows）冒烟测试：验证统一后的 app.py（三端唯一后端源）核心接口行为。

用法：
  python 脚本/smoke_api.py                    # 用 数据/ 词典的临时副本测试
  python 脚本/smoke_api.py <词典路径>          # 指定词典（完整版或精简版 .small 均可）

说明：
  - 在临时目录复制词典，测试完自动清理，绝不动原词典；
  - 覆盖前端首页、搜索、联想、列表、单词本、复习、打卡、经验、配置、笔记、导入导出、重置；
  - 全部通过退出码 0；任一项失败退出码 1 并列出失败项。
"""
import io
import os
import shutil
import sys
import tempfile
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)  # send_from_directory('.', 'index.html') 需要 cwd 在仓库根目录

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import app as server  # noqa: E402

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(("[OK] " if cond else "[FAIL] ") + name + (("  " + extra) if extra and not cond else ""))


def main():
    src_db = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "数据", "简明英汉字典增强版.db")
    if not os.path.exists(src_db):
        print(f"[错误] 词典不存在: {src_db}")
        return 2
    tmp = tempfile.mkdtemp(prefix="wordassistant_smoke_")
    try:
        db = os.path.join(tmp, "dict.db")
        print(f"复制词典到临时副本: {db}")
        shutil.copy2(src_db, db)
        server.set_db_path(db)
        server.init_db()
        c = server.app.test_client()

        # ---- 前端：桌面首页返回与手机端同一内容源的 index.html ----
        r = c.get("/")
        html = r.get_data(as_text=True)
        check("GET / 返回前端页面(200)", r.status_code == 200 and "<html" in html.lower())
        check("前端含三端共用特征(FAMOUS_QUOTES)", "FAMOUS_QUOTES" in html)

        # ---- 词典搜索 ----
        r = c.get("/api/search/apple")
        j = r.get_json(silent=True) or {}
        check("search apple 200", r.status_code == 200)
        check("search apple 字段", all(k in j for k in ("word", "phonetic", "translation")))
        r = c.get("/api/search/zzzz_not_a_word_zzzz")
        check("search 未找到 404", r.status_code == 404)
        r = c.get("/api/autocomplete?q=app")
        al = r.get_json(silent=True) or []
        check("autocomplete 返回列表", isinstance(al, list) and len(al) > 0 and "word" in al[0])

        # ---- 列表 ----
        r = c.get("/api/lists")
        lists = r.get_json(silent=True) or []
        check("GET lists 返回数组", isinstance(lists, list) and len(lists) >= 1)
        r = c.post("/api/lists", json={"name": "冒烟测试列表"})
        new_id = (r.get_json(silent=True) or {}).get("id")
        check("POST lists 创建成功", r.status_code == 200 and isinstance(new_id, int))
        if new_id:
            r = c.delete(f"/api/lists/{new_id}")
            check("DELETE lists 删除成功", (r.get_json(silent=True) or {}).get("success") is True)

        # ---- 单词本 ----
        r = c.post("/api/wordbook", json={"word": "apple", "list_id": 1})
        check("POST wordbook 加入单词", (r.get_json(silent=True) or {}).get("success") is True)
        r = c.get("/api/wordbook?list_id=1")
        wb = r.get_json(silent=True) or []
        check("GET wordbook 含 apple", any(w.get("word", "").lower() == "apple" for w in wb))
        r = c.get("/api/exp")
        check("GET exp 返回数字", isinstance((r.get_json(silent=True) or {}).get("exp"), int))
        r = c.delete("/api/wordbook/apple?list_id=1")
        check("DELETE wordbook 删除成功", (r.get_json(silent=True) or {}).get("success") is True)

        # ---- 复习 ----
        c.post("/api/wordbook", json={"word": "book", "list_id": 1})
        r = c.post("/api/review/result",
                   json={"word": "book", "list_id": 1, "correct": True, "type": "en_zh",
                         "correct_answer": "book", "translation": "n. 书"})
        check("POST review/result 正确", (r.get_json(silent=True) or {}).get("success") is True)
        r = c.post("/api/review/result",
                   json={"word": "book", "list_id": 1, "correct": False, "type": "spell", "selected": "wrong",
                         "correct_answer": "book", "translation": "n. 书"})
        check("POST review/result 错误入错题本", (r.get_json(silent=True) or {}).get("success") is True)
        # FSRS / type_stats 持久化验证（直接读临时库）
        import sqlite3 as _sq
        _conn = _sq.connect(db)
        _fs = _conn.execute("SELECT stability, difficulty, reviewed_at FROM user_words WHERE word='book'").fetchone()
        check("FSRS 字段已写入 (stability>0)", _fs is not None and (_fs[0] or 0) > 0 and _fs[2] is not None)
        _ts = json.loads(_conn.execute("SELECT value FROM settings WHERE key='type_stats'").fetchone()[0] or '{}')
        check("type_stats 累计 (en_zh.correct=1)", _ts.get("en_zh", {}).get("correct") == 1)
        check("type_stats 累计 (spell.wrong=1)", _ts.get("spell", {}).get("wrong") == 1)
        _conn.close()
        r = c.get("/api/wordbook/wrong")
        wrong = r.get_json(silent=True) or []
        check("GET 错题本含 book", any(w.get("word", "").lower() == "book" for w in wrong))
        r = c.get("/api/review?limit=5")
        check("GET review 返回数组", isinstance(r.get_json(silent=True), list))
        r = c.post("/api/review/finish")
        check("POST review/finish", (r.get_json(silent=True) or {}).get("success") is True)

        # ---- 打卡 / 进度 ----
        r = c.get("/api/streak")
        st = r.get_json(silent=True) or {}
        check("GET streak 字段", "streak" in st and "total_days" in st)
        c.post("/api/review/progress", json={"pos": 3})
        r = c.get("/api/review/progress")
        check("GET review/progress 回读", (r.get_json(silent=True) or {}).get("pos") == 3)
        c.post("/api/review/progress/clear")
        r = c.get("/api/review/progress")
        check("clear review/progress 置空", r.get_json(silent=True) is None)

        # ---- 配置 / 笔记 ----
        r = c.post("/api/config", json={"theme": "dark", "autoLimit": False})
        check("POST config 保存", (r.get_json(silent=True) or {}).get("success") is True)
        cfg = c.get("/api/config").get_json(silent=True) or {}
        check("GET config 回读 theme", cfg.get("theme") == "dark")
        check("GET config 布尔字符串化", cfg.get("autoLimit") == "false")
        c.post("/api/note", json={"content": "冒烟笔记"})
        note = c.get("/api/note").get_json(silent=True) or {}
        check("GET/POST note", note.get("content") == "冒烟笔记")

        # ---- 导入导出 ----
        c.post("/api/wordbook", json={"word": "cat", "list_id": 1})
        exp = c.get("/api/export").get_json(silent=True) or {}
        check("GET export 字段", all(k in exp for k in ("app", "word_lists", "user_words", "settings")))
        r = c.post("/api/reset", json={"mode": "words"})
        check("POST reset(mode=words)", (r.get_json(silent=True) or {}).get("success") is True)
        r = c.post("/api/import", json={"user_words": [{"word": "dog", "list_id": 1}]})
        check("POST import 导入", (r.get_json(silent=True) or {}).get("imported") == 1)

        # ---- 短语接口 ----
        r = c.get("/api/word/phrases/look")
        ph = r.get_json(silent=True) or {}
        check("GET word/phrases 字段", "word" in ph and "phrases" in ph)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [r for r in results if not r[1]]
    print("-" * 50)
    print(f"冒烟测试: {len(results) - len(failed)}/{len(results)} 通过")
    if failed:
        print("失败项:")
        for name, _, extra in failed:
            print("  [FAIL]", name, extra)
        return 1
    print("全部通过。桌面端行为即三端后端行为基线。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
