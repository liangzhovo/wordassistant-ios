import Foundation
import SQLite3

let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

/// SQLite 封装 + 数据库引导（对应 Python app.py 的 get_db / init_db）
enum DB {
    static var dbPath: String = ""
    /// 所有数据库操作串行执行（Python 端是每请求独立连接，这里同样每请求开连接 + 串行队列）
    static let queue = DispatchQueue(label: "wordassistant.db")

    // MARK: - 连接

    static func open() throws -> OpaquePointer {
        var db: OpaquePointer?
        let rc = sqlite3_open_v2(dbPath, &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX, nil)
        guard rc == SQLITE_OK, let db else {
            let msg = String(cString: sqlite3_errmsg(db))
            throw NSError(domain: "DB", code: Int(rc), userInfo: [NSLocalizedDescriptionKey: "打开数据库失败: \(msg)"])
        }
        return db
    }

    // MARK: - 查询

    @discardableResult
    static func exec(_ db: OpaquePointer, _ sql: String, _ params: [Any?] = []) throws -> Int {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw dbError(db, sql)
        }
        defer { sqlite3_finalize(stmt) }
        bind(stmt, params)
        let rc = sqlite3_step(stmt)
        guard rc == SQLITE_DONE || rc == SQLITE_ROW else {
            throw dbError(db, sql)
        }
        return Int(sqlite3_changes(db))
    }

    static func query(_ db: OpaquePointer, _ sql: String, _ params: [Any?] = []) -> [[String: Any]] {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            print("SQL prepare failed: \(sql) -> \(String(cString: sqlite3_errmsg(db)))")
            return []
        }
        defer { sqlite3_finalize(stmt) }
        bind(stmt, params)
        var rows: [[String: Any]] = []
        while sqlite3_step(stmt) == SQLITE_ROW {
            rows.append(rowDict(stmt!))
        }
        return rows
    }

    static func lastInsertId(_ db: OpaquePointer) -> Int64 {
        sqlite3_last_insert_rowid(db)
    }

    // MARK: - 辅助

    private static func bind(_ stmt: OpaquePointer?, _ params: [Any?]) {
        for (i, p) in params.enumerated() {
            let idx = Int32(i + 1)
            guard let v = p else {
                sqlite3_bind_null(stmt, idx)
                continue
            }
            if let n = v as? Int {
                sqlite3_bind_int64(stmt, idx, Int64(n))
            } else if let n = v as? Int64 {
                sqlite3_bind_int64(stmt, idx, n)
            } else if let n = v as? Double {
                sqlite3_bind_double(stmt, idx, n)
            } else if let s = v as? String {
                sqlite3_bind_text(stmt, idx, s, -1, SQLITE_TRANSIENT)
            } else if let b = v as? Bool {
                sqlite3_bind_int64(stmt, idx, b ? 1 : 0)
            } else if let d = v as? Data {
                sqlite3_bind_blob(stmt, idx, (d as NSData).bytes, Int32(d.count), SQLITE_TRANSIENT)
            } else {
                sqlite3_bind_null(stmt, idx)
            }
        }
    }

    static func rowDict(_ stmt: OpaquePointer) -> [String: Any] {
        let n = sqlite3_column_count(stmt)
        var d: [String: Any] = [:]
        for i in 0..<n {
            let name = String(cString: sqlite3_column_name(stmt, i))
            switch sqlite3_column_type(stmt, i) {
            case SQLITE_INTEGER:
                d[name] = Int(sqlite3_column_int64(stmt, i))
            case SQLITE_FLOAT:
                d[name] = sqlite3_column_double(stmt, i)
            case SQLITE_TEXT:
                if let c = sqlite3_column_text(stmt, i) {
                    d[name] = String(cString: c)
                } else {
                    d[name] = NSNull()
                }
            case SQLITE_BLOB:
                d[name] = NSNull()
            default:
                d[name] = NSNull()
            }
        }
        return d
    }

    private static func dbError(_ db: OpaquePointer, _ sql: String) -> NSError {
        NSError(domain: "DB", code: 1, userInfo: [NSLocalizedDescriptionKey: "SQL 执行失败: \(sql) -> \(String(cString: sqlite3_errmsg(db)))"])
    }

    // MARK: - 引导（对应 Python init_db）

    static func bootstrap() throws {
        let fm = FileManager.default
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        try fm.createDirectory(at: support, withIntermediateDirectories: true, attributes: nil)
        let dest = support.appendingPathComponent("简明英汉字典增强版.db")
        dbPath = dest.path
        if !fm.fileExists(atPath: dest.path) {
            guard let src = Bundle.main.url(forResource: "简明英汉字典增强版", withExtension: "db") else {
                throw NSError(domain: "DB", code: 2, userInfo: [NSLocalizedDescriptionKey: "内置词典文件缺失"])
            }
            try fm.copyItem(at: src, to: dest)
        }
        try initSchema()
    }

    static func initSchema() throws {
        let db = try open()
        defer { sqlite3_close(db) }

        // 旧表主键迁移：user_words 若主键不是复合 (word, list_id)，重建
        let exists = query(db, "SELECT name FROM sqlite_master WHERE type='table' AND name='user_words'").count > 0
        if exists {
            let hasComposite = query(db, "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_words'")
                .first
                .flatMap { $0["sql"] as? String }
                .map { $0.contains("PRIMARY KEY (word, list_id)") } ?? false
            if !hasComposite {
                try exec(db, "DROP TABLE IF EXISTS user_words")
            }
        }

        try exec(db, """
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
        """)
        try exec(db, """
            CREATE TABLE IF NOT EXISTS word_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        let listCount = query(db, "SELECT COUNT(*) AS c FROM word_lists").first?["c"] as? Int ?? 0
        if listCount == 0 {
            try exec(db, "INSERT INTO word_lists (name) VALUES (?)", ["默认列表"])
        }

        try exec(db, "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        let defaults: [[String]] = [
            ["review_mode", "learn"], ["exp", "0"], ["dailyLimit", "5"], ["autoLimit", "false"],
            ["weights", #"{"en_zh":40,"zh_en":40,"spell":20}"#], ["autoAdapt", "false"], ["theme", "system"],
            ["reminder_enabled", "false"], ["reminder_time", "09:00"]
        ]
        for kv in defaults {
            try exec(db, "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", [kv[0], kv[1]])
        }

        // SM-2 字段兼容
        let cols = query(db, "PRAGMA table_info(user_words)").compactMap { $0["name"] as? String }
        if !cols.contains("easiness_factor") {
            try exec(db, "ALTER TABLE user_words ADD COLUMN easiness_factor REAL DEFAULT 2.5")
        }
        if !cols.contains("interval") {
            try exec(db, "ALTER TABLE user_words ADD COLUMN interval INTEGER DEFAULT 0")
        }

        try exec(db, """
            CREATE TABLE IF NOT EXISTS study_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                action TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                UNIQUE(date, action)
            )
        """)
        try exec(db, """
            CREATE TABLE IF NOT EXISTS wrong_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                list_id INTEGER DEFAULT 1,
                reason TEXT,
                correct_answer TEXT,
                selected TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try exec(db, """
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
        """)
        try exec(db, """
            CREATE TABLE IF NOT EXISTS word_cache (
                word TEXT PRIMARY KEY,
                phonetic TEXT,
                translation TEXT,
                phrases TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        // 词典索引（3.3M 词条，首次启动创建一次）
        do {
            try exec(db, "CREATE INDEX IF NOT EXISTS idx_mdx_entry_nocase ON mdx(entry COLLATE NOCASE)")
        } catch {
            print("创建 mdx 索引失败: \(error)")
        }
    }

    /// 记录学习日志（对应 Python record_study_log）
    static func recordStudyLog(_ action: String) {
        let db = (try? open()) ?? nil
        guard let db else { return }
        defer { sqlite3_close(db) }
        let today = Utils.todayString()
        let rows = query(db, "SELECT id, count FROM study_log WHERE date = ? AND action = ?", [today, action])
        if let r = rows.first, let id = r["id"] as? Int, let c = r["count"] as? Int {
            try? exec(db, "UPDATE study_log SET count = ? WHERE id = ?", [c + 1, id])
        } else {
            try? exec(db, "INSERT INTO study_log (date, action, count) VALUES (?, ?, 1)", [today, action])
        }
    }
}
