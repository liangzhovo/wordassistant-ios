from flask import Flask, jsonify, request
import sqlite3
from datetime import datetime
import os, re, threading, time
import sys

app = Flask(__name__)

# 数据库路径：由 Android 端 MainActivity 启动时通过 set_db_path() 注入
DB_PATH = "简明英汉字典增强版.db"

def set_db_path(path):
    """由 Android 端调用，注入数据库绝对路径"""
    global DB_PATH
    DB_PATH = path

@app.after_request
def add_cors_headers(response):
    """WebView 从 file:// 页面访问本机 API，需要允许跨域"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    return response

def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库"""
    conn = get_db()
    cur = conn.cursor()

    # 检查现有表结构：如果主键是 word，则重建为复合主键（用于列表隔离）
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='user_words'")
    table_sql = cur.fetchone()
    if table_sql and 'PRIMARY KEY (word, list_id)' not in table_sql['sql']:
        conn.execute('DROP TABLE IF EXISTS user_words')
        conn.execute('''
            CREATE TABLE user_words (
                word TEXT NOT NULL,
                list_id INTEGER NOT NULL DEFAULT 1,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                review_count INTEGER DEFAULT 0,
                forget_count INTEGER DEFAULT 0,
                next_review DATETIME,
                mastered INTEGER DEFAULT 0,
                phonetic TEXT,
                translation TEXT,
                PRIMARY KEY (word, list_id)
            )
        ''')
    else:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_words (
                word TEXT NOT NULL,
                list_id INTEGER NOT NULL DEFAULT 1,
                added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                review_count INTEGER DEFAULT 0,
                forget_count INTEGER DEFAULT 0,
                next_review DATETIME,
                mastered INTEGER DEFAULT 0,
                phonetic TEXT,
                translation TEXT,
                PRIMARY KEY (word, list_id)
            )
        ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS word_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 始终保证默认列表（id=1）存在：即使历史版本误删过，启动时也会自动重建，
    # 避免"默认列表丢失"或"所有列表被删光"后无法恢复的问题
    cur.execute("SELECT id FROM word_lists WHERE id = 1")
    if not cur.fetchone():
        cur.execute("INSERT OR IGNORE INTO word_lists (id, name) VALUES (1, '默认列表')")

    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('review_mode', 'learn')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('exp', '0')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('dailyLimit', '5')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('autoLimit', 'false')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('weights', '{\"en_zh\":40,\"zh_en\":40,\"spell\":20}')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('autoAdapt', 'false')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('theme', 'system')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('reminder_enabled', 'false')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('reminder_time', '09:00')")

    # SM-2 间隔重复新增字段（兼容已有旧数据库）
    def _add_col(table, col, ddl):
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    _add_col('user_words', 'easiness_factor', 'REAL DEFAULT 2.5')
    _add_col('user_words', 'interval', 'INTEGER DEFAULT 0')

    # 学习日志表
    conn.execute('''
        CREATE TABLE IF NOT EXISTS study_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            action TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            UNIQUE(date, action)
        )
    ''')

    # 错题记录表（记录每次答错的详情）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS wrong_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL,
            list_id INTEGER DEFAULT 1,
            reason TEXT,
            correct_answer TEXT,
            selected TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 错题本表（当前错题，独立存储，答错进、答对出）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS wrong_book (
            word TEXT NOT NULL,
            list_id INTEGER DEFAULT 1,
            wrong_count INTEGER DEFAULT 1,
            last_reason TEXT,
            correct_answer TEXT,
            selected TEXT,
            translation TEXT,
            first_wrong DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_wrong DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (word, list_id)
        )
    ''')

    # 单词缓存表（加入单词本时抓取完整信息，错题本/思维导图从此读取）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS word_cache (
            word TEXT PRIMARY KEY,
            phonetic TEXT,
            translation TEXT,
            phrases TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 词库索引
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mdx_entry_nocase ON mdx(entry COLLATE NOCASE)")
    except Exception:
        pass

    conn.commit()
    conn.close()

# 记录学习日志
def record_study_log(action):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, count FROM study_log WHERE date = ? AND action = ?", (today, action))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE study_log SET count = count + 1 WHERE id = ?", (row['id'],))
    else:
        cur.execute("INSERT INTO study_log (date, action, count) VALUES (?, ?, 1)", (today, action))
    conn.commit()
    conn.close()

# 获取月度学习日志 API
@app.route('/api/study_log/month')
def get_study_log_month():
    month = request.args.get('month')
    if not month:
        return jsonify({})
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT date, action, count FROM study_log WHERE date LIKE ?", (month + '%',))
    rows = cur.fetchall()
    conn.close()
    result = {}
    for row in rows:
        if row['date'] not in result:
            result[row['date']] = {'add': 0, 'review': 0}
        result[row['date']][row['action']] = row['count']
    return jsonify(result)

# 清洗释义
def clean_paraphrase(text):
    if not text: return {'phonetic': '', 'translation': ''}
    
    # 【核心修复】如果是精简库（已经以 n. v. adj. 开头），直接返回，防止二次切割丢失词性
    if re.match(r'^(n|v|vt|vi|adj|adv|prep|pron|conj|interj|num|art|aux)\.', text.strip()):
        return {'phonetic': '', 'translation': text.strip()}
        
    text = re.sub(r'-K\d+\s*', '', text)
    text = re.sub(r'-\d+\s*', '', text)
    text = text.replace('`1`','').replace('`2`','').replace('`3`','').replace('`4`','').replace('</br>','；')
    phonetic = ''
    m = re.search(r'\[(.*?)\]', text)
    if m:
        phonetic = m.group(1)
        text = re.sub(r'\[.*?\]', '', text)
    first = text.split('；')[0].strip()
    first = re.sub(r'^a\.\s+', 'adj. ', first)
    parts = first.split(' ', 1)
    if len(parts) > 1:
        if re.match(r'^(n|v|vt|vi|adj|adv|prep|pron|conj|interj|num|art|aux)\.', parts[1]):
            first = parts[1]
        else:
            first = parts[1]
    return {'phonetic': phonetic, 'translation': first}

# 列表 API
@app.route('/api/lists', methods=['GET'])
def get_lists():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM word_lists ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/lists', methods=['POST'])
def create_list():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': '列表名称不能为空'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO word_lists (name) VALUES (?)", (name,))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({'id': new_id, 'name': name})

@app.route('/api/lists/<int:list_id>', methods=['DELETE'])
def delete_list(list_id):
    conn = get_db()
    cur = conn.cursor()
    if list_id == 1:
        conn.close()
        return jsonify({'error': '默认列表不能删除'}), 400
    # 至少保留一个列表，防止全部列表被删光后默认列表 id 漂移
    cur.execute("SELECT COUNT(*) FROM word_lists")
    if cur.fetchone()[0] <= 1:
        conn.close()
        return jsonify({'error': '至少保留一个列表'}), 400
    cur.execute("DELETE FROM user_words WHERE list_id = ?", (list_id,))
    cur.execute("DELETE FROM word_lists WHERE id = ?", (list_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# 单词 API
@app.route('/api/wordbook', methods=['GET'])
def get_wordbook():
    list_id = request.args.get('list_id', type=int)
    conn = get_db()
    cur = conn.cursor()
    if list_id:
        cur.execute("SELECT * FROM user_words WHERE list_id = ? ORDER BY word ASC", (list_id,))
    else:
        cur.execute("SELECT * FROM user_words ORDER BY word ASC")
    rows = cur.fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if not item['translation'] or not item['phonetic']:
            cur.execute("SELECT entry, paraphrase FROM mdx WHERE entry = ? COLLATE NOCASE", (item['word'].lower().strip(),))
            w_row = cur.fetchone()
            if w_row:
                details = clean_paraphrase(w_row['paraphrase'])
                item['phonetic'] = details['phonetic']
                item['translation'] = details['translation']
                cur.execute("UPDATE user_words SET phonetic=?, translation=? WHERE word=? AND list_id=?", 
                            (item['phonetic'], item['translation'], item['word'], item['list_id']))
        result.append(item)
    conn.commit()
    conn.close()
    return jsonify(result)

@app.route('/api/wordbook', methods=['POST'])
def add_word():
    data = request.json
    word = data.get('word').lower().strip()
    list_id = data.get('list_id', 1)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT entry, paraphrase FROM mdx WHERE entry = ? COLLATE NOCASE", (word,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '单词不存在'}), 404
    details = clean_paraphrase(row['paraphrase'])
    phonetic = details['phonetic']
    translation = details['translation']
    cur.execute("INSERT OR IGNORE INTO user_words (word, list_id, phonetic, translation) VALUES (?, ?, ?, ?)", 
                (word, list_id, phonetic, translation))
    cur.execute("UPDATE settings SET value = CAST(value AS INTEGER) + 5 WHERE key = 'exp'")

    # 抓取该词的词组/复合词并缓存到 word_cache（供错题本/思维导图使用）
    try:
        import json as _json
        phrases = []
        # 词组（word + 空格）
        cur.execute("SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE ORDER BY LENGTH(entry) LIMIT 30", (word + ' %',))
        for pr in cur.fetchall():
            pc = clean_paraphrase(pr['paraphrase'])
            phrases.append({'phrase': pr['entry'], 'meaning': pc['translation']})
        # 复合词（word 开头不含空格且非单词本身）
        cur.execute("SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE AND entry != ? COLLATE NOCASE AND entry NOT LIKE '% %' ORDER BY LENGTH(entry) LIMIT 10", (word + '%', word))
        for pr in cur.fetchall():
            pc = clean_paraphrase(pr['paraphrase'])
            phrases.append({'phrase': pr['entry'], 'meaning': pc['translation']})
        cur.execute("INSERT OR REPLACE INTO word_cache (word, phonetic, translation, phrases, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                    (word, phonetic, translation, _json.dumps(phrases, ensure_ascii=False)))
    except Exception:
        pass  # 缓存失败不影响加入单词本

    conn.commit()
    conn.close()
    
    record_study_log('add')
    
    return jsonify({'success': True})

@app.route('/api/wordbook/<word>', methods=['DELETE'])
def delete_word(word):
    list_id = request.args.get('list_id', type=int)
    conn = get_db()
    cur = conn.cursor()
    if list_id:
        cur.execute("DELETE FROM user_words WHERE word = ? AND list_id = ?", (word.lower().strip(), list_id))
    else:
        cur.execute("DELETE FROM user_words WHERE word = ?", (word.lower().strip(),))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# 复习 API
@app.route('/api/review', methods=['GET'])
def get_review_words():
    list_id = request.args.get('list_id', type=int)
    conn = get_db()
    cur = conn.cursor()
    if list_id:
        cur.execute("SELECT word FROM user_words WHERE list_id = ? AND mastered = 0 AND (next_review IS NULL OR next_review <= datetime('now')) ORDER BY next_review ASC LIMIT 20", (list_id,))
    else:
        cur.execute("SELECT word FROM user_words WHERE mastered = 0 AND (next_review IS NULL OR next_review <= datetime('now')) ORDER BY next_review ASC LIMIT 20")
    rows = cur.fetchall()
    conn.close()
    return jsonify([r['word'] for r in rows])

def sm2_update(ef, interval, correct):
    """SM-2 间隔重复算法，返回 (new_ef, new_interval_days)。
    ef 为易度因子(easiness factor)，初始 2.5；interval 为当前复习间隔(天)。"""
    if correct:
        # 答对：质量分简化为 4
        new_ef = ef + (0.1 - (5 - 4) * (0.08 + (5 - 4) * 0.02))
        new_ef = max(1.3, new_ef)
        if interval == 0:
            new_interval = 1
        elif interval == 1:
            new_interval = 6
        else:
            new_interval = round(interval * new_ef)
    else:
        # 答错：间隔重置，易度下降
        new_ef = max(1.3, ef - 0.2)
        new_interval = 1
    return new_ef, new_interval

def _upsert_wrong_book(cur, word, list_id, forgot, correct_answer, selected, translation):
    """加入/更新错题本（答错或忘记时调用）"""
    cur.execute('''INSERT INTO wrong_book (word, list_id, wrong_count, last_reason, correct_answer, selected, translation, last_wrong)
        VALUES (?, ?, 1, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(word, list_id) DO UPDATE SET
            wrong_count = wrong_count + 1,
            last_reason = excluded.last_reason,
            correct_answer = excluded.correct_answer,
            selected = excluded.selected,
            translation = excluded.translation,
            last_wrong = datetime('now')''',
        (word, list_id, 'forgot' if forgot else 'wrong', correct_answer, selected, translation or ''))

@app.route('/api/review/result', methods=['POST'])
def review_result():
    data = request.json
    word = data.get('word', '').lower().strip()
    correct = data.get('correct', False)
    forgot = data.get('forgot', False)
    selected = data.get('selected')          # 用户选择的答案（答错时）
    correct_answer = data.get('correct_answer')  # 正确答案
    list_id = data.get('list_id')
    if not word:
        return jsonify({'error': '缺少单词'}), 400
    conn = get_db()
    cur = conn.cursor()
    # 解析列表：'all'/None 时找词实际所在列表
    if str(list_id) == 'all' or list_id is None:
        cur.execute("SELECT list_id FROM user_words WHERE word = ? ORDER BY forget_count DESC LIMIT 1", (word,))
        r = cur.fetchone()
        list_id = r['list_id'] if r else 1
    cur.execute("SELECT review_count, forget_count, mastered, easiness_factor, interval FROM user_words WHERE word = ? AND list_id = ?", (word, list_id))
    row = cur.fetchone()
    if not row:
        # 词不在该列表：找词的其他列表
        cur.execute("SELECT list_id FROM user_words WHERE word = ? LIMIT 1", (word,))
        r2 = cur.fetchone()
        if r2:
            list_id = r2['list_id']
            cur.execute("SELECT review_count, forget_count, mastered, easiness_factor, interval FROM user_words WHERE word = ? AND list_id = ?", (word, list_id))
            row = cur.fetchone()
    if not row:
        # 词不在任何列表：插入（并记录错题）
        cur.execute("INSERT INTO user_words (word, list_id, forget_count, review_count) VALUES (?, ?, ?, 0)",
                    (word, list_id, 1 if (not correct or forgot) else 0))
        if not correct or forgot:
            cur.execute("INSERT INTO wrong_logs (word, list_id, reason, correct_answer, selected) VALUES (?, ?, ?, ?, ?)",
                        (word, list_id, 'forgot' if forgot else 'wrong', correct_answer, selected))
            _upsert_wrong_book(cur, word, list_id, forgot, correct_answer, selected, data.get('translation'))
        conn.commit()
        conn.close()
        record_study_log('review')
        return jsonify({'success': True, 'inserted': True})
    # 正常更新记忆曲线
    review_count, forget_count, mastered = row['review_count'], row['forget_count'], row['mastered']
    ef = row['easiness_factor'] or 2.5
    interval = row['interval'] or 0
    is_correct = correct and not forgot
    new_ef, new_interval = sm2_update(ef, interval, is_correct)
    if is_correct:
        review_count += 1
        if forget_count > 0: forget_count = max(0, forget_count - 1)
        cur.execute("UPDATE settings SET value = CAST(value AS INTEGER) + 2 WHERE key = 'exp'")
        # 连续答对且间隔达到 30 天以上视为已掌握
        if new_interval >= 30:
            mastered = 1
        next_review = f"+{new_interval} day"
        # 答对：移出错题本
        cur.execute("DELETE FROM wrong_book WHERE word = ? AND list_id = ?", (word, list_id))
    else:
        forget_count += 1
        review_count = max(0, review_count - 1)
        mastered = 0
        next_review = "+1 day"
        # 记录错因
        cur.execute("INSERT INTO wrong_logs (word, list_id, reason, correct_answer, selected) VALUES (?, ?, ?, ?, ?)",
                    (word, list_id, 'forgot' if forgot else 'wrong', correct_answer, selected))
        # 加入错题本
        _upsert_wrong_book(cur, word, list_id, forgot, correct_answer, selected, data.get('translation'))
    cur.execute('''UPDATE user_words SET review_count=?, forget_count=?, mastered=?, easiness_factor=?, interval=?, next_review=datetime('now', ?) WHERE word=? AND list_id=?''',
                (review_count, forget_count, mastered, new_ef, new_interval, next_review, word, list_id))
    conn.commit()
    conn.close()
    
    record_study_log('review')
    
    return jsonify({'success': True})

@app.route('/api/review/finish', methods=['POST'])
def finish_review():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE settings SET value = CAST(value AS INTEGER) + 10 WHERE key = 'exp'")
    conn.commit()
    conn.close()
    
    record_study_log('review')
    
    return jsonify({'success': True})

# 重置数据（mode=all 清空所有；mode=words 只删除所有单词）
@app.route('/api/reset', methods=['POST'])
def reset_all():
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'all')
    conn = get_db()
    cur = conn.cursor()
    try:
        if mode == 'words':
            # 只删除所有单词（保留列表、设置、学习记录）
            cur.execute("DELETE FROM user_words")
        else:
            # 清空用户单词和错题数据
            cur.execute("DELETE FROM user_words")
            # 清空学习日志
            cur.execute("DELETE FROM study_log")
            # 清空列表，重建默认列表
            cur.execute("DELETE FROM word_lists")
            cur.execute("INSERT INTO word_lists (name) VALUES ('默认列表')")
            # 重置设置到默认值
            defaults = {
                'review_mode': 'learn', 'exp': '0', 'dailyLimit': '5',
                'autoLimit': 'false', 'weights': '{"en_zh":40,"zh_en":40,"spell":20}',
                'autoAdapt': 'false', 'theme': 'system',
                'reminder_enabled': 'false', 'reminder_time': '09:00'
            }
            cur.execute("DELETE FROM settings")
            for k, v in defaults.items():
                cur.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500
    conn.close()
    return jsonify({'success': True})

# 错题本 API（forget_count > 0 的单词）
@app.route('/api/wordbook/wrong', methods=['GET'])
def get_wrong_words():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM wrong_book ORDER BY last_wrong DESC, wrong_count DESC")
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['forget_count'] = d.get('wrong_count', 1)  # 兼容前端字段
            result.append(d)
    except Exception:
        # 表不存在（旧版本）时退回老的查询
        cur.execute("SELECT * FROM user_words WHERE forget_count > 0 ORDER BY forget_count DESC, word ASC")
        rows = cur.fetchall()
        result = [dict(r) for r in rows]
    conn.close()
    return jsonify(result)

@app.route('/api/wordbook/<word>/clear_wrong', methods=['POST'])
def clear_wrong(word):
    list_id = request.args.get('list_id', type=int) or 1
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE user_words SET forget_count = 0 WHERE word = ? AND list_id = ?", (word.lower().strip(), list_id))
    # 同时从独立错题本移除
    cur.execute("DELETE FROM wrong_book WHERE word = ?", (word.lower().strip(),))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# 连续打卡统计 API
@app.route('/api/streak')
def get_streak():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM study_log ORDER BY date DESC")
    dates = [r['date'] for r in cur.fetchall()]
    conn.close()
    from datetime import datetime, timedelta
    date_set = set(dates)
    streak = 0
    d = datetime.now()
    if d.strftime('%Y-%m-%d') not in date_set:
        d -= timedelta(days=1)  # 今天还没学习，从昨天开始算
    while d.strftime('%Y-%m-%d') in date_set:
        streak += 1
        d -= timedelta(days=1)
    return jsonify({'streak': streak, 'total_days': len(date_set)})

# 导出/导入单词本（备份与分享）
@app.route('/api/export')
def export_data():
    list_id = request.args.get('list_id', type=int)
    conn = get_db()
    cur = conn.cursor()
    if list_id:
        lists = cur.execute("SELECT * FROM word_lists WHERE id = ?", (list_id,)).fetchall()
        words = cur.execute("SELECT * FROM user_words WHERE list_id = ? ORDER BY word", (list_id,)).fetchall()
    else:
        lists = cur.execute("SELECT * FROM word_lists ORDER BY id").fetchall()
        words = cur.execute("SELECT * FROM user_words ORDER BY word").fetchall()
    settings = cur.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return jsonify({
        'app': 'WordAssistant',
        'version': 1,
        'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'exported_list_id': list_id,
        'word_lists': [dict(r) for r in lists],
        'user_words': [dict(r) for r in words],
        'settings': {r['key']: r['value'] for r in settings}
    })

@app.route('/api/import', methods=['POST'])
def import_data():
    data = request.json
    if not data or 'user_words' not in data:
        return jsonify({'error': '数据格式错误'}), 400
    target_list_id = data.get('target_list_id')  # 导入目标列表
    conn = get_db()
    cur = conn.cursor()
    try:
        # 仅当未指定目标列表时，才导入 JSON 里的列表定义
        # （指定了 target_list_id 时忽略列表创建，全部融合到目标列表）
        if not target_list_id and 'word_lists' in data and isinstance(data['word_lists'], list):
            for lst in data['word_lists']:
                cur.execute("INSERT OR IGNORE INTO word_lists (id, name, created_at) VALUES (?, ?, ?)",
                            (lst.get('id'), lst.get('name', '导入列表'),
                             lst.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))))
        imported = 0
        for w in data['user_words']:
            # 如果指定了目标列表，统一导入到该列表
            list_id = target_list_id if target_list_id else w.get('list_id', 1)
            cur.execute('''INSERT OR IGNORE INTO user_words
                (word, list_id, added_date, review_count, forget_count, next_review, mastered, phonetic, translation, easiness_factor, interval)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (w.get('word'), list_id, w.get('added_date'),
                 w.get('review_count', 0), w.get('forget_count', 0), w.get('next_review'),
                 w.get('mastered', 0), w.get('phonetic'), w.get('translation'),
                 w.get('easiness_factor', 2.5), w.get('interval', 0)))
            imported += 1
        if 'settings' in data and isinstance(data['settings'], dict):
            for k, v in data['settings'].items():
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500
    conn.close()
    return jsonify({'success': True, 'imported': imported})

# 搜索/配置/经验 API
@app.route('/api/search/<word>')
def search_word(word):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT entry, paraphrase FROM mdx WHERE entry = ? COLLATE NOCASE", (word.lower().strip(),))
    row = cur.fetchone()
    conn.close()
    if row:
        c = clean_paraphrase(row['paraphrase'])
        return jsonify({'word': row['entry'], 'phonetic': c['phonetic'], 'translation': c['translation']})
    return jsonify({'error': '未找到'}), 404

@app.route('/api/word/phrases/<word>')
def word_phrases(word):
    """查询指定词的词组和复合词（优先读缓存，无缓存时实时查并缓存）"""
    import json as _json
    conn = get_db()
    cur = conn.cursor()
    w = word.lower().strip()
    # 优先读 word_cache
    cur.execute("SELECT phrases FROM word_cache WHERE word = ? COLLATE NOCASE", (w,))
    cached = cur.fetchone()
    if cached and cached['phrases']:
        try:
            phrases = _json.loads(cached['phrases'])
            conn.close()
            return jsonify({'word': w, 'phrases': phrases, 'cached': True})
        except Exception:
            pass
    # 实时查询
    cur.execute("SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE ORDER BY LENGTH(entry) LIMIT 60", (w + ' %',))
    rows = cur.fetchall()
    phrases = []
    for r in rows:
        try:
            meaning = clean_paraphrase(r['paraphrase'])['translation'] if r['paraphrase'] else ''
        except Exception:
            meaning = ''
        phrases.append({'phrase': r['entry'], 'meaning': meaning})
    # 缓存本次结果
    try:
        cur.execute("INSERT OR REPLACE INTO word_cache (word, phonetic, translation, phrases, updated_at) VALUES (?, '', '', ?, datetime('now'))",
                    (w, _json.dumps(phrases, ensure_ascii=False)))
        conn.commit()
    except Exception:
        pass
    conn.close()
    return jsonify({'word': w, 'phrases': phrases})

@app.route('/api/autocomplete')
def autocomplete():
    q = request.args.get('q','').lower().strip()
    if not q: return jsonify([])
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE ORDER BY LENGTH(entry) LIMIT 20", (q + '%',))
    rows = cur.fetchall()
    conn.close()
    results = []
    for r in rows:
        c = clean_paraphrase(r['paraphrase'])
        trans = c['translation']
        if not re.search(r'[\u4e00-\u9fa5]', trans): continue
        if len(trans) > 40: trans = trans[:40] + '...'
        results.append({'word': r['entry'], 'phonetic': c['phonetic'], 'translation': trans})
        if len(results) >= 5: break
    return jsonify(results)

@app.route('/api/exp', methods=['GET'])
def get_exp():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='exp'")
    row = cur.fetchone()
    conn.close()
    return jsonify({'exp': int(row['value']) if row else 0})

# 复习进度保存（中断后可继续）
@app.route('/api/review/progress', methods=['GET'])
def get_review_progress():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM settings WHERE key='review_progress'")
        row = cur.fetchone()
        conn.close()
        if row and row['value']:
            import json
            try:
                return jsonify(json.loads(row['value']))
            except Exception:
                pass
    except Exception:
        conn.close()
    return jsonify(None)

@app.route('/api/review/progress', methods=['POST'])
def save_review_progress():
    import json
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('review_progress', ?)", (json.dumps(data),))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/review/progress/clear', methods=['POST'])
def clear_review_progress():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM settings WHERE key='review_progress'")
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/config', methods=['GET'])
def get_config():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    rows = cur.fetchall()
    conn.close()
    return jsonify({r['key']: r['value'] for r in rows})

@app.route('/api/config', methods=['POST'])
def save_config():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    for k,v in data.items():
        # 确保布尔值存为字符串（兼容字符串 'true'/'false' 与布尔值）
        # 注意：字符串 'false' 在 Python 中是 truthy，不能用 `'true' if v else 'false'`，
        # 否则会把 'false' 误存为 'true'，导致复选框取消后又被勾选。
        if k in ['autoLimit', 'autoAdapt']:
            v = 'true' if str(v).lower() == 'true' else 'false'
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# 记事本 API（单个草稿本，用于粘贴保存 AI 生成的 JSON/文本）
@app.route('/api/note', methods=['GET'])
def get_note():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key='note'")
    row = cur.fetchone()
    conn.close()
    return jsonify({'content': row['value'] if row else ''})

@app.route('/api/note', methods=['POST'])
def save_note():
    data = request.json
    content = data.get('content', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('note', ?)", (content,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/')
def index():
    # 返回前端页面
    return "Word Assistant API Server is running!"

def main():
    """Android 端入口：由 MainActivity 在后台线程中调用"""
    init_db()
    print("🚀 Flask API 服务启动，端口 5000")
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False, threaded=True)

if __name__ == '__main__':
    main()