import Foundation

/// 纯逻辑工具：释义清洗 / SM-2 / 日期，与 Python app.py 行为一致
enum Utils {
    static let posRegex = "^(n|v|vt|vi|adj|adv|prep|pron|conj|interj|num|art|aux)\\."

    /// 清洗释义（对应 Python clean_paraphrase）
    static func cleanParaphrase(_ text: String?) -> (phonetic: String, translation: String) {
        guard let t = text, !t.isEmpty else { return ("", "") }
        let s = t.trimmingCharacters(in: .whitespacesAndNewlines)

        func cleanPos(_ line: String) -> String {
            var l = line.replacingOccurrences(of: "^a\\.\\s+", with: "adj. ", options: [.regularExpression, .anchored])
            // 去掉教材兜底词条里的 [reference:xxx] 残留标记（如 upcycle 的 [reference:101]）
            l = l.replacingOccurrences(of: "\\[reference:[^\\]]*\\]", with: "", options: .regularExpression)
            return l.trimmingCharacters(in: .whitespacesAndNewlines)
        }

        // 新格式（ECDICT 学生版）：[音标]词性. 释义（每行一个词性组，首行为最常用义项）
        if let m = s.range(of: "\\[(.*?)\\]", options: .regularExpression) {
            let sub = String(s[m])
            let phonetic = sub.count >= 2 ? String(sub.dropFirst().dropLast()) : ""
            let rest = s.replacingOccurrences(of: "\\[.*?\\]", with: "", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let first = rest.split(separator: "\n").first.map(String.init) ?? rest
            return (phonetic, cleanPos(first))
        }
        if s.range(of: posRegex, options: [.regularExpression, .anchored]) != nil {
            let first = s.split(separator: "\n").first.map(String.init) ?? s
            return ("", cleanPos(first))
        }

        // 旧 MDX 格式兜底（历史库）：原清洗流程
        var o = t
        o = o.replacingOccurrences(of: "-K\\d+\\s*", with: "", options: .regularExpression)
        o = o.replacingOccurrences(of: "-\\d+\\s*", with: "", options: .regularExpression)
        o = o.replacingOccurrences(of: "`1`", with: "").replacingOccurrences(of: "`2`", with: "")
        o = o.replacingOccurrences(of: "`3`", with: "").replacingOccurrences(of: "`4`", with: "")
        o = o.replacingOccurrences(of: "</br>", with: "；")

        var phonetic = ""
        if let m = o.range(of: "\\[(.*?)\\]", options: .regularExpression) {
            let sub = String(o[m])
            if sub.count >= 2 {
                phonetic = String(sub.dropFirst().dropLast())
            }
        }
        o = o.replacingOccurrences(of: "\\[.*?\\]", with: "", options: .regularExpression)

        var first = o.components(separatedBy: "；")[0].trimmingCharacters(in: .whitespacesAndNewlines)
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
            var newEf = ef + (0.1 - (5.0 - 4.0) * (0.08 + (5.0 - 4.0) * 0.02))
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

    // MARK: - FSRS 间隔重复调度（对应 Python fsrs.py，移植自 FSRS4Anki v6.1.1）

    static let fsrsW: [Double] = [0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001,
                                  1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014,
                                  1.8729, 0.5425, 0.0912, 0.0658, 0.1542]
    static let fsrsRequestRetention = 0.9
    static let fsrsMaximumInterval = 36500
    static let fsrsDecay = -fsrsW[20]
    static let fsrsFactor = pow(0.9, 1 / fsrsDecay) - 1

    /// 一次作答后的调度更新；correct=True -> good(3)，否则 again(1)
    static func fsrsSchedule(correct: Bool, stability: Double?, difficulty: Double?, elapsedDays: Double) -> (s: Double, d: Double, interval: Int) {
        let rating = correct ? 3 : 1
        let newS: Double
        let newD: Double
        if let s = stability, let d = difficulty {
            let r = fsrsForgettingCurve(elapsedDays: elapsedDays, stability: s)
            if correct {
                newS = fsrsNextRecallStability(difficulty: d, stability: s, r: r, rating: rating)
            } else {
                newS = fsrsNextForgetStability(difficulty: d, stability: s, r: r)
            }
            newD = fsrsNextDifficulty(d, rating: rating)
        } else {
            newS = fsrsInitStability(rating: rating)
            newD = fsrsInitDifficulty(rating: rating)
        }
        return (round2(newS), round2(newD), fsrsNextInterval(newS))
    }

    private static func round2(_ x: Double) -> Double { (x * 100).rounded() / 100 }

    static func fsrsInitStability(rating: Int) -> Double {
        max(fsrsW[rating - 1], 0.1)
    }

    static func fsrsInitDifficulty(rating: Int) -> Double {
        round2(fsrsConstrainDifficulty(fsrsW[4] - exp(fsrsW[5] * Double(rating - 1)) + 1))
    }

    static func fsrsForgettingCurve(elapsedDays: Double, stability: Double) -> Double {
        if stability <= 0 || elapsedDays < 0 { return 1.0 }
        return pow(1 + fsrsFactor * elapsedDays / stability, fsrsDecay)
    }

    static func fsrsNextInterval(_ stability: Double) -> Int {
        let ivl = stability / fsrsFactor * (pow(fsrsRequestRetention, 1 / fsrsDecay) - 1)
        return Int(min(max(ivl.rounded(), 1), Double(fsrsMaximumInterval)))
    }

    private static func fsrsConstrainDifficulty(_ d: Double) -> Double {
        min(max((d * 100).rounded() / 100, 1), 10)
    }

    private static func fsrsLinearDamping(deltaD: Double, oldD: Double) -> Double {
        deltaD * (10 - oldD) / 9
    }

    private static func fsrsMeanReversion(_ initV: Double, _ current: Double) -> Double {
        fsrsW[7] * initV + (1 - fsrsW[7]) * current
    }

    static func fsrsNextDifficulty(_ d: Double, rating: Int) -> Double {
        let deltaD = -fsrsW[6] * Double(rating - 3)
        let nxt = d + fsrsLinearDamping(deltaD: deltaD, oldD: d)
        return round2(fsrsConstrainDifficulty(fsrsMeanReversion(fsrsInitDifficulty(rating: 4), nxt)))
    }

    static func fsrsNextRecallStability(difficulty d: Double, stability s: Double, r: Double, rating: Int) -> Double {
        let hardPenalty = rating == 2 ? fsrsW[15] : 1
        let easyBonus = rating == 4 ? fsrsW[16] : 1
        return s * (1 + exp(fsrsW[8]) * (11 - d) * pow(s, -fsrsW[9]) * (exp((1 - r) * fsrsW[10]) - 1) * hardPenalty * easyBonus)
    }

    static func fsrsNextForgetStability(difficulty d: Double, stability s: Double, r: Double) -> Double {
        let sMin = s / exp(fsrsW[17] * fsrsW[18])
        return min(fsrsW[11] * pow(d, -fsrsW[12]) * (pow(s + 1, fsrsW[13]) - 1) * exp((1 - r) * fsrsW[14]), sMin)
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
