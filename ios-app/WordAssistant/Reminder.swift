import UserNotifications

/// 每日学习提醒（对应 Android AlarmManager + 通知）
final class Reminder {
    private static let identifier = "dailyReminder"

    func schedule(hour: Int, minute: Int, enabled: Bool) {
        let center = UNUserNotificationCenter.current()
        if !enabled {
            center.removePendingNotificationRequests(withIdentifiers: [Reminder.identifier])
            return
        }
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = "🦉 该背单词啦"
            content.body = "今日单词任务在等你，坚持打卡！"
            content.sound = .default
            var components = DateComponents()
            components.hour = max(0, min(23, hour))
            components.minute = max(0, min(59, minute))
            let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: true)
            let request = UNNotificationRequest(identifier: Reminder.identifier, content: content, trigger: trigger)
            center.add(request)
        }
    }
}
