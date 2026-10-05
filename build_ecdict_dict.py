# -*- coding: utf-8 -*-
"""
从 ECDICT ecdict.csv 构建「单词助手」学生版词典库。

生成两个库（表结构与旧库完全兼容，app 代码仅需适配释义清洗逻辑）：
  FULL  = 简明英汉字典增强版.db            （全量：有中文释义的词条 + 词形变化展开）
  SMALL = 简明英汉字典增强版.db.small      （学生核心：中考 zk + 牛津三千 oxford）

paraphrase 统一格式（每行一个词性组，第一行为最常用义项）：
  [音标]词性. 释义
  词性. 释义
  ...
示例：about -> [ә'baut]prep. 在...周围, 大约, 有关, 关于\nadv. 大约, 四处, 在附近, 周围

用法：python build_ecdict_dict.py [ecdict.csv 路径]
"""
import csv, os, re, sqlite3, sys, time

sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.abspath(__file__))
FULL = os.path.join(ROOT, '简明英汉字典增强版.db.new')      # 先输出 .new，验证后替换
SMALL = os.path.join(ROOT, 'android-app', 'app', 'src', 'main', 'assets', '简明英汉字典增强版.db.small.new')

# 词条类型/变体标注（exchange 字段展开用）
EXCHANGE_LABEL = {
    'p': '过去式', 'd': '过去分词', 'i': '现在分词', '3': '第三人称单数',
    's': '复数', 'r': '比较级', 't': '最高级', '0': '', '1': '',
}
VAR_TYPE_HEAD = {'p': 'v.', 'd': 'v.', 'i': 'v.', '3': 'v.', 's': 'n.', 'r': 'adj.', 't': 'adj.'}


def clean_pos(line):
    """去掉 [学科] 前缀标签（[经] [计] [网络] 等），保留词性标注"""
    line = re.sub(r'^\[[^\]]*\]\s*', '', line.strip())
    return line.strip()


# 词性映射：translation 行前缀 -> pos 字段占比键
POS_MAP = {
    'n': 'n', 'v': 'v', 'vt': 'v', 'vi': 'v',
    'a': 'a', 'adj': 'a', 'ad': 'ad', 'adv': 'ad',
    'prep': 'prep', 'pron': 'pron', 'pro': 'pron', 'conj': 'conj',
    'int': 'int', 'interj': 'int', 'num': 'num', 'art': 'art', 'aux': 'aux',
}
# 学习优先词性顺序（pos 占比缺失时的兜底）：动词/形容词在前，名词殿后
POS_PRIORITY = {'v': 0, 'a': 1, 'n': 2, 'ad': 3, 'prep': 4,
                'pron': 5, 'conj': 6, 'int': 7, 'num': 8, 'art': 9, 'aux': 10}
POS_RE = r'^(n|v|vt|vi|a|adj|ad|adv|prep|pron|pro|conj|int|interj|num|art|aux)\.'
# 变体标注行：如 "v.take 的过去式"
VAR_ANNOT_RE = re.compile(r'^[a-z]+\.\w+\s+的')


def parse_pos_rank(pos_str):
    """'n:46/v:54' -> {'n': 46.0, 'v': 54.0}"""
    d = {}
    for seg in (pos_str or '').split('/'):
        seg = seg.strip()
        if ':' in seg:
            k, v = seg.split(':', 1)
            try:
                d[k.strip()] = float(v)
            except Exception:
                pass
    return d


def fmt_paraphrase(phonetic, translation, pos_str):
    """转成 [音标]词性. 释义 多行格式；按 pos 词性使用占比降序排列（最常见词性在最前）。
    注意：ECDICT CSV 中 translation 的行分隔是字面 '\\n'，先转成真换行。"""
    lines = []
    if phonetic:
        lines.append('[' + phonetic + ']')
    rank = parse_pos_rank(pos_str)
    tagged, untagged = [], []
    for ln in (translation or '').replace('\\n', '\n').split('\n'):
        ln = clean_pos(ln)
        if not ln:
            continue
        m = re.match(POS_RE, ln)
        if m and m.group(1) in POS_MAP:
            key = POS_MAP[m.group(1)]
            if VAR_ANNOT_RE.match(ln):
                tagged.append((None, ln))     # 变体标注行，放最后
            else:
                tagged.append((key, ln))
        else:
            untagged.append(ln)               # 无词性行（[学科] 内容等），放最后
    if rank:
        # 有 pos 占比：按占比降序（同键稳定保持原序）
        tagged.sort(key=lambda x: (0, -rank.get(x[0], 1e9), POS_PRIORITY.get(x[0], 99)) if x[0] else (1, 0, 0))
    else:
        # 无 pos 占比：默认保持 ECDICT 原序；仅当第一行是名词(n.)且后续存在
        # 义项明显更多的动词(v)或形容词(a)行时，把该常用词性行提前
        # （避免 "good → n. 善行, 好处, 利益" 这类冷门名词义排首）。
        def _count_senses(ln):
            return ln.count(',') + 1
        first = tagged[0] if tagged else None
        if first and first[0] == 'n':
            n_count = _count_senses(first[1])
            v_best = max([(k, ln) for k, ln in tagged if k == 'v'], key=lambda x: _count_senses(x[1]), default=None)
            a_best = max([(k, ln) for k, ln in tagged if k == 'a'], key=lambda x: _count_senses(x[1]), default=None)
            cand = None
            if v_best and _count_senses(v_best[1]) > n_count:
                cand = v_best
            elif a_best and _count_senses(a_best[1]) > n_count:
                cand = a_best
            if cand:
                tagged = [cand] + [x for x in tagged if x != cand]
    for k, ln in tagged:
        lines.append(ln)
    for ln in untagged:
        lines.append(ln)
    if len(lines) <= 1:
        return None
    return '\n'.join(lines)


def exchange_entries(word, exchange):
    """解析 exchange 字段，返回 [(变体, 原词, 类型)]。0/1 是 lemma 信息，跳过。"""
    out = []
    if not exchange:
        return out
    for item in exchange.split('/'):
        item = item.strip()
        if not item or ':' not in item:
            continue
        typ, var = item.split(':', 1)
        typ = typ.strip()
        var = var.strip()
        if typ in ('0', '1') or not var or var.lower() == word.lower() or ' ' in var:
            continue
        out.append((var, word, typ))
    return out


def safe_int(s):
    try:
        return int(s or 0)
    except Exception:
        return 0


def build(src, db_path, only_core=False, expand_exchange=False):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('CREATE TABLE mdx (entry TEXT NOT NULL, paraphrase TEXT NOT NULL)')
    cur.execute('CREATE INDEX idx_mdx_entry_nocase ON mdx(entry COLLATE NOCASE)')
    # 学生元数据表：保留 tag/oxford/frq 等信息，便于后续升级与筛选
    cur.execute('''CREATE TABLE ecdict_meta (
        word TEXT PRIMARY KEY, phonetic TEXT, pos TEXT, collins TEXT,
        oxford TEXT, tag TEXT, bnc INTEGER, frq INTEGER, exchange TEXT)''')

    is_core = None
    if only_core:
        def is_core(row):
            tag = (row.get('tag') or '').split()
            return 'zk' in tag or (row.get('oxford') or '').strip() == '1'

    t0 = time.time()
    n = meta_n = 0
    var_n = 0
    with open(src, encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        batch = []
        for row in reader:
            word = (row.get('word') or '').strip()
            if not word:
                continue
            if only_core and not is_core(row):
                continue
            phonetic = (row.get('phonetic') or '').strip()
            para = fmt_paraphrase(phonetic, (row.get('translation') or '').strip(), (row.get('pos') or '').strip())
            if para is None:
                continue
            batch.append((word, para))
            cur.execute('INSERT OR IGNORE INTO ecdict_meta VALUES (?,?,?,?,?,?,?,?,?)',
                        (word, phonetic, (row.get('pos') or '').strip(),
                         (row.get('collins') or '').strip(), (row.get('oxford') or '').strip(),
                         (row.get('tag') or '').strip(), safe_int(row.get('bnc')),
                         safe_int(row.get('frq')), (row.get('exchange') or '').strip()))
            meta_n += 1
            n += 1
            if expand_exchange:
                for var, orig, typ in exchange_entries(word, (row.get('exchange') or '').strip()):
                    head = VAR_TYPE_HEAD.get(typ, '')
                    var_para = para + '\n' + head + orig + ' 的' + EXCHANGE_LABEL.get(typ, '变体')
                    batch.append((var, var_para))
                    var_n += 1
            if len(batch) >= 5000:
                cur.executemany('INSERT INTO mdx VALUES (?,?)', batch)
                batch = []
                conn.commit()
                sys.stdout.write(f'\r  已写入 {n} 词条 (变体 {var_n})  {time.time()-t0:.0f}s')
                sys.stdout.flush()
        if batch:
            cur.executemany('INSERT INTO mdx VALUES (?,?)', batch)
            conn.commit()
    cur.execute('ANALYZE')
    conn.commit()
    rows = cur.execute('SELECT COUNT(*) FROM mdx').fetchone()[0]
    size = os.path.getsize(db_path)
    conn.close()
    print(f'\n完成: {db_path}')
    print(f'  词条(含变体) {rows} | 原词 {n} | 变体 {var_n} | 元数据 {meta_n} | 大小 {size/1048576:.1f} MB')
    return rows


if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get('TEMP', ''), 'ecdict.csv')
    print('数据源:', src, '存在:', os.path.exists(src))
    if not os.path.exists(src):
        sys.exit(1)
    print('\n===== 构建完整版 =====')
    build(src, FULL, only_core=False, expand_exchange=True)
    print('\n===== 构建精简版（中考+牛津三千）=====')
    build(src, SMALL, only_core=True, expand_exchange=False)
