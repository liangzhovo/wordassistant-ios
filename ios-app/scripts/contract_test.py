# -*- coding: utf-8 -*-
"""契约测试：验证 iOS Swift 移植使用的 SQL 在词典库上有效。
用法: python ios-app/scripts/contract_test.py [数据库路径]
"""
import sqlite3, os, sys

repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
db_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    repo, "android-app", "app", "src", "main", "assets", "简明英汉字典增强版.db.small")

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row
cur = con.cursor()

def q(sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()

ok = True
def check(name, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ((" " + extra) if extra else ""))
    if not cond:
        ok = False

rows = q("SELECT entry, paraphrase FROM mdx WHERE entry = ? COLLATE NOCASE", ("hello",))
check("search hello", len(rows) == 1)

rows = q("SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE ORDER BY LENGTH(entry) LIMIT 30", ("run %",))
check("phrases 'run %'", len(rows) > 0)

rows = q("SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE AND entry != ? COLLATE NOCASE AND entry NOT LIKE '% %' ORDER BY LENGTH(entry) LIMIT 10", ("run%", "run"))
check("compounds 'run%'", len(rows) > 0)

rows = q("SELECT word FROM user_words WHERE mastered = 0 AND (next_review IS NULL OR next_review <= datetime('now')) ORDER BY next_review ASC LIMIT 20")
check("review queue", len(rows) >= 0)

rows = q("SELECT value FROM settings WHERE key='exp'")
check("settings exp", len(rows) == 1)

rows = q("SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE ORDER BY LENGTH(entry) LIMIT 20", ("appl%",))
check("autocomplete appl%", len(rows) > 0)

rows = q("SELECT entry, paraphrase FROM mdx WHERE entry = ? COLLATE NOCASE", ("HELLO",))
check("search HELLO nocase", len(rows) == 1)

rows = q("SELECT datetime('now', '+6 day') AS d")
check("datetime modifier", rows and rows[0]["d"] > "2020-01-01")

try:
    q("INSERT OR IGNORE INTO user_words (word, list_id, review_count, forget_count) VALUES ('zzztest', 1, 0, 0)")
    check("import insert", True)
    q("DELETE FROM user_words WHERE word='zzztest'")
except Exception as e:
    check("import insert", False, str(e))

con.close()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
