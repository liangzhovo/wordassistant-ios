import Foundation

/// 纯逻辑工具：释义清洗 / SM-2 / 日期，与 Python app.py 行为一致
enum Utils {
    static let posRegex = "^(n|v|vt|vi|adj|adv|prep|pron|conj|interj|num|art|aux)\\."

    /// 清洗释义（对应 Python clean_paraphrase）
    static func cleanParaphrase(_ text: String?) -> (phonetic: String, translation: String) {
        guard let t = text, !t.isEmpty else { return ("", "") }
        let stripped = t.trimmingCharacters(in: .whitespacesAndNewlines)

        // 精简库释义已以词性开头，直接返回，防止二次切割丢失词性
        if stripped.range(of: posRegex, options: [.regularExpression, .anchored]) != nil {
            return ("", stripped)
        }

        var s = t
        s = s.replacingOccurrences(of: "-K\\d+\\s*", with: "", options: .regularExpression)
        s = s.replacingOccurrences(of: "-\\d+\\s*", with: "", options: .regularExpression)
        s = s.replacingOccurrences(of: "`1`", with: "")
        s = s.replacingOccurrences(of: "`2`", with: "")
        s = s.replacingOccurrences(of: "`3`", with: "")
        s = s.replacingOccurrences(of: "`4`", with: "")
        s = s.replacingOccurrences(of: "</br>", with: "；")

        var phonetic = ""
        if let m = s.range(of: "\\[(.*?)\\]", options: .regularExpression) {
            let sub = String(s[m])
            if sub.count >= 2 {
                phonetic = String(sub.dropFirst().dropLast())
            }
        }
        s = s.replacingOccurrences(of: "\\[.*?\\]", with: "", options: .regularExpression)

        var first = s.components(separatedBy: "；")[0].trimmingCharacters(in: .whitespacesAndNewlines)
        first = first.replacingOccurrences(of: "^a\\.\\s+", with: "adj. ", options: [.regularExpression, .anchored])

        let parts = first.split(separator: " ", maxSplits: 1).map(String.init)
        if parts.count > 1 {
            first = parts[1]
        }
        return (phonetic, first)
    }

    /// SM-2 间隔重复（对应 Python sm2_update）
    static func sm2Update(ef: Double, interval: Int, correct: Bool) -> (ef: Double, interval: Int) {
        if correct {
            var newEf = ef + (0.1 - (5 - 4) * (0.08 + (5 - 4) * 0.02))
            newEf = max(1.3, newEf)
            let newInterval: Int
            if interval == 0 {
                newInterval = 1
            } else if interval == 1 {
                newInterval = 6
            } else {
                newInterval = Int((Double(interval) * newEf).rounded())
            }
            return (newEf, newInterval)
        } else {
            return (max(1.3, ef - 0.2), 1)
        }
    }

    /// 是否包含中文
    static func containsChinese(_ s: String) -> Bool {
        s.range(of: "[\\u4e00-\\u9fa5]", options: .regularExpression) != nil
    }

    /// 本地时区 yyyy-MM-dd
    static func todayString() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f.string(from: Date())
    }

    /// 本地时区 yyyy-MM-dd HH:mm:ss
    static func nowString() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f.string(from: Date())
    }

    /// 截断释义（对应 Python autocomplete 的 len>40 处理）
    static func truncate(_ s: String, _ n: Int) -> String {
        s.count > n ? String(s.prefix(n - 1)) + "..." : s
    }
}
