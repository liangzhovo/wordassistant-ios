import Foundation

/// API 响应
struct APIResponse {
    let status: Int
    let json: Any?

    static func json(_ value: Any?, status: Int = 200) -> APIResponse {
        APIResponse(status: status, json: value)
    }
    static func error(_ status: Int, _ message: String) -> APIResponse {
        APIResponse(status: status, json: ["error": message])
    }
    static let notFound = APIResponse(status: 404, json: ["error": "接口不存在"])
}

/// 路由与端点实现（逐行对应 Python app.py）
enum Api {

    static func route(method: String, path: String, query: [String: String], body: [String: Any]?) -> APIResponse {
        let comps = path.split(separator: "/").map(String.init)
        do {
            switch (method, comps) {
            case ("GET", ["api", "study_log", "month"]):
                return try studyLogMonth(query)
            case ("GET", ["api", "lists"]):
                return try getLists()
            case ("POST", ["api", "lists"]):
                return try createList(body)
            case ("DELETE", ["api", "lists", let id]):
                return try deleteList(Int(id))
            case ("GET", ["api", "wordbook"]):
                return try getWordbook(query)
            case ("POST", ["api", "wordbook"]):
                return try addWord(body)
            case ("DELETE", ["api", "wordbook", let word]):
                return try deleteWord(word, query)
            case ("GET", ["api", "review"]):
                return try getReview(query)
            case ("POST", ["api", "review", "result"]):
                return try reviewResult(body)
            case ("POST", ["api", "review", "finish"]):
                return try finishReview()
            case ("POST", ["api", "reset"]):
                return try resetAll(body)
            case ("GET", ["api", "wordbook", "wrong"]):
                return try getWrongWords()
            case ("POST", ["api", "wordbook", let word, "clear_wrong"]):
                return try clearWrong(word, query)
            case ("GET", ["api", "streak"]):
                return getStreak()
            case ("GET", ["api", "export"]):
                return try exportData(query)
            case ("POST", ["api", "import"]):
                return try importData(body)
            case ("GET", ["api", "search", let word]):
                return try searchWord(word)
            case ("GET", ["api", "word", "phrases", let word]):
                return try wordPhrases(word)
            case ("GET", ["api", "autocomplete"]):
                return try autocomplete(query)
            case ("GET", ["api", "exp"]):
                return try getExp()
            case ("GET", ["api", "review", "progress"]):
                return getReviewProgress()
            case ("POST", ["api", "review", "progress"]):
                return try saveReviewProgress(body)
            case ("POST", ["api", "review", "progress", "clear"]):
                return try clearReviewProgress()
            case ("GET", ["api", "config"]):
                return try getConfig()
            case ("POST", ["api", "config"]):
                return try saveConfig(body)
            case ("GET", ["api", "note"]):
                return try getNote()
            case ("POST", ["api", "note"]):
                return try saveNote(body)
            default:
                return .notFound
            }
        } catch {
            return .error(500, "\(error)")
        }
    }

    // MARK: - 工具

    private static func openDB() throws -> OpaquePointer {
        try DB.open()
    }

    /// 加入/更新错题本（对应 Python _upsert_wrong_book）
    private static func upsertWrongBook(_ db: OpaquePointer, word: String, listId: Int, forgot: Bool,
                                        correctAnswer: String?, selected: String?, translation: String?) throws {
        try DB.exec(db, """
            INSERT INTO wrong_book (word, list_id, wrong_count, last_reason, correct_answer, selected, translation, last_wrong)
            VALUES (?, ?, 1, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(word, list_id) DO UPDATE SET
                wrong_count = wrong_count + 1,
                last_reason = excluded.last_reason,
                correct_answer = excluded.correct_answer,
                selected = excluded.selected,
                translation = excluded.translation,
                last_wrong = datetime('now')
        """, [word, listId, forgot ? "forgot" : "wrong", correctAnswer ?? "", selected ?? "", translation ?? ""])
    }

    private static func jsonString(_ value: Any) -> String {
        if let data = try? JSONSerialization.data(withJSONObject: value) {
            return String(data: data, encoding: .utf8) ?? "[]"
        }
        return "[]"
    }

    // MARK: - 学习日志

    static func studyLogMonth(_ query: [String: String]) throws -> APIResponse {
        guard let month = query["month"], !month.isEmpty else { return .json([:]) }
        let db = try openDB()
        defer { sqlite3_close(db) }
        let rows = DB.query(db, "SELECT date, action, count FROM study_log WHERE date LIKE ?", [month + "%"])
        var result: [String: Any] = [:]
        for r in rows {
            let date = r["date"] as? String ?? ""
            let action = r["action"] as? String ?? ""
            let count = r["count"] as? Int ?? 0
            if result[date] == nil {
                result[date] = ["add": 0, "review": 0]
            }
            var entry = result[date] as! [String: Any]
            entry[action] = count
            result[date] = entry
        }
        return .json(result)
    }

    // MARK: - 列表

    static func getLists() throws -> APIResponse {
        let db = try openDB()
        defer { sqlite3_close(db) }
        return .json(DB.query(db, "SELECT * FROM word_lists ORDER BY id ASC"))
    }

    static func createList(_ body: [String: Any]?) throws -> APIResponse {
        let name = (body?["name"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return .error(400, "列表名称不能为空") }
        let db = try openDB()
        defer { sqlite3_close(db) }
        try DB.exec(db, "INSERT INTO word_lists (name) VALUES (?)", [name])
        let newId = DB.lastInsertId(db)
        return .json(["id": Int(newId), "name": name])
    }

    static func deleteList(_ listId: Int?) throws -> APIResponse {
        guard let listId else { return .error(400, "列表 ID 无效") }
        if listId == 1 {
            return .error(400, "默认列表不能删除")
        }
        let db = try openDB()
        defer { sqlite3_close(db) }
        try DB.exec(db, """
            DELETE FROM user_words WHERE list_id = ? AND word IN (SELECT word FROM user_words WHERE list_id = 1)
        """, [listId])
        try DB.exec(db, "UPDATE user_words SET list_id = 1 WHERE list_id = ?", [listId])
        try DB.exec(db, "DELETE FROM word_lists WHERE id = ?", [listId])
        return .json(["success": true])
    }

    // MARK: - 单词本

    static func getWordbook(_ query: [String: String]) throws -> APIResponse {
        let listId = Int(query["list_id"] ?? "")
        let db = try openDB()
        defer { sqlite3_close(db) }
        let rows: [[String: Any]]
        if let listId {
            rows = DB.query(db, "SELECT * FROM user_words WHERE list_id = ? ORDER BY word ASC", [listId])
        } else {
            rows = DB.query(db, "SELECT * FROM user_words ORDER BY word ASC")
        }
        var result: [[String: Any]] = []
        for var item in rows {
            let translation = item["translation"] as? String ?? ""
            let phonetic = item["phonetic"] as? String ?? ""
            if translation.isEmpty || phonetic.isEmpty {
                let word = item["word"] as? String ?? ""
                if let w = DB.query(db, "SELECT entry, paraphrase FROM mdx WHERE entry = ? COLLATE NOCASE", [word.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)]).first {
                    let d = Utils.cleanParaphrase(w["paraphrase"] as? String)
                    item["phonetic"] = d.phonetic
                    item["translation"] = d.translation
                    let listId = item["list_id"] as? Int ?? 1
                    try? DB.exec(db, "UPDATE user_words SET phonetic=?, translation=? WHERE word=? AND list_id=?",
                                 [d.phonetic, d.translation, item["word"] ?? "", listId])
                }
            }
            result.append(item)
        }
        return .json(result)
    }

    static func addWord(_ body: [String: Any]?) throws -> APIResponse {
        let word = (body?["word"] as? String ?? "").lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let listId = body?["list_id"] as? Int ?? 1
        let db = try openDB()
        defer { sqlite3_close(db) }
        guard let row = DB.query(db, "SELECT entry, paraphrase FROM mdx WHERE entry = ? COLLATE NOCASE", [word]).first else {
            return .error(404, "单词不存在")
        }
        let d = Utils.cleanParaphrase(row["paraphrase"] as? String)
        try DB.exec(db, "INSERT OR IGNORE INTO user_words (word, list_id, phonetic, translation) VALUES (?, ?, ?, ?)",
                    [word, listId, d.phonetic, d.translation])
        try DB.exec(db, "UPDATE settings SET value = CAST(value AS INTEGER) + 5 WHERE key = 'exp'")

        // 抓取词组/复合词缓存（失败不影响加入单词本）
        do {
            var phrases: [[String: String]] = []
            for pr in DB.query(db, "SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE ORDER BY LENGTH(entry) LIMIT 30", [word + " %"]) {
                let pc = Utils.cleanParaphrase(pr["paraphrase"] as? String)
                phrases.append(["phrase": pr["entry"] as? String ?? "", "meaning": pc.translation])
            }
            for pr in DB.query(db, "SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE AND entry != ? COLLATE NOCASE AND entry NOT LIKE '% %' ORDER BY LENGTH(entry) LIMIT 10", [word + "%", word]) {
                let pc = Utils.cleanParaphrase(pr["paraphrase"] as? String)
                phrases.append(["phrase": pr["entry"] as? String ?? "", "meaning": pc.translation])
            }
            try DB.exec(db, "INSERT OR REPLACE INTO word_cache (word, phonetic, translation, phrases, updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
                        [word, d.phonetic, d.translation, jsonString(phrases)])
        } catch {
            print("词组缓存失败: \(error)")
        }
        DB.recordStudyLog("add")
        return .json(["success": true])
    }

    static func deleteWord(_ word: String, _ query: [String: String]) throws -> APIResponse {
        let w = word.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let listId = Int(query["list_id"] ?? "")
        let db = try openDB()
        defer { sqlite3_close(db) }
        if let listId {
            try DB.exec(db, "DELETE FROM user_words WHERE word = ? AND list_id = ?", [w, listId])
        } else {
            try DB.exec(db, "DELETE FROM user_words WHERE word = ?", [w])
        }
        return .json(["success": true])
    }

    // MARK: - 复习

    static func getReview(_ query: [String: String]) throws -> APIResponse {
        let listId = Int(query["list_id"] ?? "")
        let db = try openDB()
        defer { sqlite3_close(db) }
        let rows: [[String: Any]]
        if let listId {
            rows = DB.query(db, """
                SELECT word FROM user_words WHERE list_id = ? AND mastered = 0 AND (next_review IS NULL OR next_review <= datetime('now')) ORDER BY next_review ASC LIMIT 20
            """, [listId])
        } else {
            rows = DB.query(db, """
                SELECT word FROM user_words WHERE mastered = 0 AND (next_review IS NULL OR next_review <= datetime('now')) ORDER BY next_review ASC LIMIT 20
            """)
        }
        return .json(rows.map { $0["word"] ?? "" })
    }

    static func reviewResult(_ body: [String: Any]?) throws -> APIResponse {
        guard let body else { return .error(400, "缺少请求体") }
        let word = (body["word"] as? String ?? "").lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let correct = body["correct"] as? Bool ?? false
        let forgot = body["forgot"] as? Bool ?? false
        let selected = body["selected"] as? String
        let correctAnswer = body["correct_answer"] as? String
        let translation = body["translation"] as? String
        guard !word.isEmpty else { return .error(400, "缺少单词") }

        // 解析 list_id：'all' / None 时按实际列表
        var listId: Int = -1
        if let li = body["list_id"] {
            if let n = li as? Int {
                listId = n
            } else if let s = li as? String {
                listId = (s == "all") ? -1 : (Int(s) ?? 1)
            } else if let d = li as? Double {
                listId = Int(d)
            }
        }

        let db = try openDB()
        defer { sqlite3_close(db) }

        if listId == -1 {
            let r = DB.query(db, "SELECT list_id FROM user_words WHERE word = ? ORDER BY forget_count DESC LIMIT 1", [word]).first
            listId = (r?["list_id"] as? Int) ?? 1
        }

        var row = DB.query(db, "SELECT review_count, forget_count, mastered, easiness_factor, interval FROM user_words WHERE word = ? AND list_id = ?", [word, listId]).first
        if row == nil {
            if let r2 = DB.query(db, "SELECT list_id FROM user_words WHERE word = ? LIMIT 1", [word]).first,
               let lid = r2["list_id"] as? Int {
                listId = lid
                row = DB.query(db, "SELECT review_count, forget_count, mastered, easiness_factor, interval FROM user_words WHERE word = ? AND list_id = ?", [word, listId]).first
            }
        }

        if row == nil {
            // 词不在任何列表：插入并记录错题
            let fc = (!correct || forgot) ? 1 : 0
            try DB.exec(db, "INSERT INTO user_words (word, list_id, forget_count, review_count) VALUES (?, ?, ?, 0)", [word, listId, fc])
            if !correct || forgot {
                try DB.exec(db, "INSERT INTO wrong_logs (word, list_id, reason, correct_answer, selected) VALUES (?, ?, ?, ?, ?)",
                            [word, listId, forgot ? "forgot" : "wrong", correctAnswer ?? "", selected ?? ""])
                try upsertWrongBook(db, word: word, listId: listId, forgot: forgot, correctAnswer: correctAnswer, selected: selected, translation: translation)
            }
            DB.recordStudyLog("review")
            return .json(["success": true, "inserted": true])
        }

        var reviewCount = row?["review_count"] as? Int ?? 0
        var forgetCount = row?["forget_count"] as? Int ?? 0
        var mastered = row?["mastered"] as? Int ?? 0
        let ef = row?["easiness_factor"] as? Double ?? 2.5
        let interval = row?["interval"] as? Int ?? 0
        let isCorrect = correct && !forgot
        let (newEf, newInterval) = Utils.sm2Update(ef: ef, interval: interval, correct: isCorrect)

        if isCorrect {
            reviewCount += 1
            if forgetCount > 0 { forgetCount = max(0, forgetCount - 1) }
            try DB.exec(db, "UPDATE settings SET value = CAST(value AS INTEGER) + 2 WHERE key = 'exp'")
            if newInterval >= 30 { mastered = 1 }
            try DB.exec(db, "DELETE FROM wrong_book WHERE word = ? AND list_id = ?", [word, listId])
        } else {
            forgetCount += 1
            reviewCount = max(0, reviewCount - 1)
            mastered = 0
            try DB.exec(db, "INSERT INTO wrong_logs (word, list_id, reason, correct_answer, selected) VALUES (?, ?, ?, ?, ?)",
                        [word, listId, forgot ? "forgot" : "wrong", correctAnswer ?? "", selected ?? ""])
            try upsertWrongBook(db, word: word, listId: listId, forgot: forgot, correctAnswer: correctAnswer, selected: selected, translation: translation)
        }
        try DB.exec(db, """
            UPDATE user_words SET review_count=?, forget_count=?, mastered=?, easiness_factor=?, interval=?, next_review=datetime('now', ?) WHERE word=? AND list_id=?
        """, [reviewCount, forgetCount, mastered, newEf, newInterval, isCorrect ? "+\(newInterval) day" : "+1 day", word, listId])
        DB.recordStudyLog("review")
        return .json(["success": true])
    }

    static func finishReview() throws -> APIResponse {
        let db = try openDB()
        defer { sqlite3_close(db) }
        try DB.exec(db, "UPDATE settings SET value = CAST(value AS INTEGER) + 10 WHERE key = 'exp'")
        DB.recordStudyLog("review")
        return .json(["success": true])
    }

    // MARK: - 重置

    static func resetAll(_ body: [String: Any]?) throws -> APIResponse {
        let mode = body?["mode"] as? String ?? "all"
        let db = try openDB()
        defer { sqlite3_close(db) }
        do {
            if mode == "words" {
                try DB.exec(db, "DELETE FROM user_words")
            } else {
                try DB.exec(db, "DELETE FROM user_words")
                try DB.exec(db, "DELETE FROM study_log")
                try DB.exec(db, "DELETE FROM word_lists")
                try DB.exec(db, "INSERT INTO word_lists (name) VALUES ('默认列表')")
                let defaults: [[String]] = [
                    ["review_mode", "learn"], ["exp", "0"], ["dailyLimit", "5"], ["autoLimit", "false"],
                    ["weights", #"{"en_zh":40,"zh_en":40,"spell":20}"#], ["autoAdapt", "false"], ["theme", "system"],
                    ["reminder_enabled", "false"], ["reminder_time", "09:00"]
                ]
                try DB.exec(db, "DELETE FROM settings")
                for kv in defaults {
                    try DB.exec(db, "INSERT INTO settings (key, value) VALUES (?, ?)", [kv[0], kv[1]])
                }
            }
            return .json(["success": true])
        } catch {
            return .error(500, "\(error)")
        }
    }

    // MARK: - 错题本

    static func getWrongWords() throws -> APIResponse {
        let db = try openDB()
        defer { sqlite3_close(db) }
        var result: [[String: Any]] = []
        do {
            for var d in DB.query(db, "SELECT * FROM wrong_book ORDER BY last_wrong DESC, wrong_count DESC") {
                d["forget_count"] = d["wrong_count"] ?? 1
                result.append(d)
            }
        } catch {
            // 表不存在（旧版本）退回旧查询
            result = DB.query(db, "SELECT * FROM user_words WHERE forget_count > 0 ORDER BY forget_count DESC, word ASC")
        }
        return .json(result)
    }

    static func clearWrong(_ word: String, _ query: [String: String]) throws -> APIResponse {
        let w = word.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let listId = Int(query["list_id"] ?? "") ?? 1
        let db = try openDB()
        defer { sqlite3_close(db) }
        try DB.exec(db, "UPDATE user_words SET forget_count = 0 WHERE word = ? AND list_id = ?", [w, listId])
        try DB.exec(db, "DELETE FROM wrong_book WHERE word = ?", [w])
        return .json(["success": true])
    }

    // MARK: - 打卡

    static func getStreak() -> APIResponse {
        guard let db = try? openDB() else { return .json(["streak": 0, "total_days": 0]) }
        defer { sqlite3_close(db) }
        let rows = DB.query(db, "SELECT DISTINCT date FROM study_log ORDER BY date DESC")
        var dateSet = Set<String>()
        for r in rows {
            if let d = r["date"] as? String { dateSet.insert(d) }
        }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        var streak = 0
        var d = Date()
        if !dateSet.contains(f.string(from: d)) {
            d = Calendar.current.date(byAdding: .day, value: -1, to: d) ?? d
        }
        while dateSet.contains(f.string(from: d)) {
            streak += 1
            d = Calendar.current.date(byAdding: .day, value: -1, to: d) ?? d
        }
        return .json(["streak": streak, "total_days": dateSet.count])
    }

    // MARK: - 导出 / 导入

    static func exportData(_ query: [String: String]) throws -> APIResponse {
        let listId = Int(query["list_id"] ?? "")
        let db = try openDB()
        defer { sqlite3_close(db) }
        let lists: [[String: Any]]
        let words: [[String: Any]]
        if let listId {
            lists = DB.query(db, "SELECT * FROM word_lists WHERE id = ?", [listId])
            words = DB.query(db, "SELECT * FROM user_words WHERE list_id = ? ORDER BY word", [listId])
        } else {
            lists = DB.query(db, "SELECT * FROM word_lists ORDER BY id")
            words = DB.query(db, "SELECT * FROM user_words ORDER BY word")
        }
        let settingsRows = DB.query(db, "SELECT key, value FROM settings")
        var settings: [String: String] = [:]
        for r in settingsRows {
            if let k = r["key"] as? String, let v = r["value"] as? String {
                settings[k] = v
            }
        }
        return .json([
            "app": "WordAssistant",
            "version": 1,
            "exported_at": Utils.nowString(),
            "exported_list_id": listId ?? NSNull(),
            "word_lists": lists,
            "user_words": words,
            "settings": settings
        ])
    }

    static func importData(_ body: [String: Any]?) throws -> APIResponse {
        guard let data = body, data["user_words"] != nil else {
            return .error(400, "数据格式错误")
        }
        let targetListId = data["target_list_id"] as? Int
        let db = try openDB()
        defer { sqlite3_close(db) }
        var imported = 0
        do {
            if targetListId == nil, let wordLists = data["word_lists"] as? [[String: Any]] {
                for lst in wordLists {
                    let lid = lst["id"] as? Int ?? 1
                    let name = lst["name"] as? String ?? "导入列表"
                    let createdAt = lst["created_at"] as? String ?? Utils.todayString() + " 00:00:00"
                    try DB.exec(db, "INSERT OR IGNORE INTO word_lists (id, name, created_at) VALUES (?, ?, ?)", [lid, name, createdAt])
                }
            }
            if let userWords = data["user_words"] as? [[String: Any]] {
                for w in userWords {
                    let listId = targetListId ?? (w["list_id"] as? Int ?? 1)
                    try DB.exec(db, """
                        INSERT OR IGNORE INTO user_words
                        (word, list_id, added_date, review_count, forget_count, next_review, mastered, phonetic, translation, easiness_factor, interval)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        w["word"], listId,
                        w["added_date"] ?? Utils.todayString() + " 00:00:00",
                        w["review_count"] as? Int ?? 0,
                        w["forget_count"] as? Int ?? 0,
                        w["next_review"] ?? "",
                        w["mastered"] as? Int ?? 0,
                        w["phonetic"] ?? "",
                        w["translation"] ?? "",
                        w["easiness_factor"] as? Double ?? 2.5,
                        w["interval"] as? Int ?? 0
                    ])
                    imported += 1
                }
            }
            if let settings = data["settings"] as? [String: Any] {
                for (k, v) in settings {
                    try DB.exec(db, "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", [k, String(describing: v)])
                }
            }
            return .json(["success": true, "imported": imported])
        } catch {
            return .error(500, "\(error)")
        }
    }

    // MARK: - 搜索

    static func searchWord(_ word: String) throws -> APIResponse {
        let w = word.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let db = try openDB()
        defer { sqlite3_close(db) }
        guard let row = DB.query(db, "SELECT entry, paraphrase FROM mdx WHERE entry = ? COLLATE NOCASE", [w]).first else {
            return .error(404, "未找到")
        }
        let d = Utils.cleanParaphrase(row["paraphrase"] as? String)
        return .json(["word": row["entry"] ?? "", "phonetic": d.phonetic, "translation": d.translation])
    }

    static func wordPhrases(_ word: String) throws -> APIResponse {
        let w = word.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let db = try openDB()
        defer { sqlite3_close(db) }
        // 优先读缓存
        if let cached = DB.query(db, "SELECT phrases FROM word_cache WHERE word = ? COLLATE NOCASE", [w]).first,
           let phrasesStr = cached["phrases"] as? String, !phrasesStr.isEmpty,
           let parsed = try? JSONSerialization.jsonObject(with: Data(phrasesStr.utf8)) as? [[String: String]] {
            return .json(["word": w, "phrases": parsed, "cached": true])
        }
        var phrases: [[String: String]] = []
        for r in DB.query(db, "SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE ORDER BY LENGTH(entry) LIMIT 60", [w + " %"]) {
            let meaning = Utils.cleanParaphrase(r["paraphrase"] as? String).translation
            phrases.append(["phrase": r["entry"] as? String ?? "", "meaning": meaning])
        }
        try? DB.exec(db, "INSERT OR REPLACE INTO word_cache (word, phonetic, translation, phrases, updated_at) VALUES (?, '', '', ?, datetime('now'))",
                     [w, jsonString(phrases)])
        return .json(["word": w, "phrases": phrases])
    }

    static func autocomplete(_ query: [String: String]) throws -> APIResponse {
        let q = (query["q"] ?? "").lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return .json([]) }
        let db = try openDB()
        defer { sqlite3_close(db) }
        let rows = DB.query(db, "SELECT entry, paraphrase FROM mdx WHERE entry LIKE ? COLLATE NOCASE ORDER BY LENGTH(entry) LIMIT 20", [q + "%"])
        var results: [[String: Any]] = []
        for r in rows {
            let c = Utils.cleanParaphrase(r["paraphrase"] as? String)
            let trans = c.translation
            guard Utils.containsChinese(trans) else { continue }
            let t = trans.count > 40 ? Utils.truncate(trans, 40) : trans
            results.append(["word": r["entry"] ?? "", "phonetic": c.phonetic, "translation": t])
            if results.count >= 5 { break }
        }
        return .json(results)
    }

    // MARK: - 经验 / 进度 / 配置 / 记事本

    static func getExp() throws -> APIResponse {
        let db = try openDB()
        defer { sqlite3_close(db) }
        let row = DB.query(db, "SELECT value FROM settings WHERE key='exp'").first
        let exp = (row?["value"] as? String).flatMap(Int.init) ?? 0
        return .json(["exp": exp])
    }

    static func getReviewProgress() -> APIResponse {
        guard let db = try? openDB() else { return .json(NSNull()) }
        defer { sqlite3_close(db) }
        let row = DB.query(db, "SELECT value FROM settings WHERE key='review_progress'").first
        if let v = row?["value"] as? String, !v.isEmpty,
           let data = v.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(with: data) {
            return .json(obj)
        }
        return .json(NSNull())
    }

    static func saveReviewProgress(_ body: [String: Any]?) throws -> APIResponse {
        let db = try openDB()
        defer { sqlite3_close(db) }
        let value = jsonString(body ?? [:])
        try DB.exec(db, "INSERT OR REPLACE INTO settings (key, value) VALUES ('review_progress', ?)", [value])
        return .json(["success": true])
    }

    static func clearReviewProgress() throws -> APIResponse {
        let db = try openDB()
        defer { sqlite3_close(db) }
        try DB.exec(db, "DELETE FROM settings WHERE key='review_progress'")
        return .json(["success": true])
    }

    static func getConfig() throws -> APIResponse {
        let db = try openDB()
        defer { sqlite3_close(db) }
        var result: [String: String] = [:]
        for r in DB.query(db, "SELECT key, value FROM settings") {
            if let k = r["key"] as? String, let v = r["value"] as? String {
                result[k] = v
            }
        }
        return .json(result)
    }

    static func saveConfig(_ body: [String: Any]?) throws -> APIResponse {
        guard let data = body else { return .json(["success": true]) }
        let db = try openDB()
        defer { sqlite3_close(db) }
        for (k, v) in data {
            var value = String(describing: v)
            if k == "autoLimit" || k == "autoAdapt" {
                value = (String(describing: v).lowercased() == "true") ? "true" : "false"
            }
            try DB.exec(db, "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", [k, value])
        }
        return .json(["success": true])
    }

    static func getNote() throws -> APIResponse {
        let db = try openDB()
        defer { sqlite3_close(db) }
        let row = DB.query(db, "SELECT value FROM settings WHERE key='note'").first
        return .json(["content": row?["value"] as? String ?? ""])
    }

    static func saveNote(_ body: [String: Any]?) throws -> APIResponse {
        let content = body?["content"] as? String ?? ""
        let db = try openDB()
        defer { sqlite3_close(db) }
        try DB.exec(db, "INSERT OR REPLACE INTO settings (key, value) VALUES ('note', ?)", [content])
        return .json(["success": true])
    }
}
