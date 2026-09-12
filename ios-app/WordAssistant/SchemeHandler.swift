import Foundation
import WebKit

/// 自定义 URL scheme 处理：wordapp://localhost 提供页面与 API
/// （WKURLSchemeHandler 拿不到 POST body，前端已把 body 放到 _body query 参数）
final class SchemeHandler: NSObject, WKURLSchemeHandler {

    private let lock = NSLock()
    private var boxes: [ObjectIdentifier: TaskBox] = [:]

    /// 缓存页面（92KB，只读一次）
    private var pageData: Data?

    private final class TaskBox {
        let task: WKURLSchemeTask
        var cancelled = false
        init(_ task: WKURLSchemeTask) { self.task = task }
    }

    override init() {
        super.init()
        if let p = Bundle.main.path(forResource: "index", ofType: "html") {
            pageData = FileManager.default.contents(atPath: p)
        }
    }

    // MARK: - WKURLSchemeHandler

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        let box = TaskBox(task)
        lock.lock()
        boxes[ObjectIdentifier(task)] = box
        lock.unlock()

        guard let url = task.request.url else {
            finish(box, status: 400, data: Data(), mime: "application/json", url: URL(string: "wordapp://localhost/")!)
            return
        }
        let comps = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let path = comps?.path ?? "/"

        if path == "/" || path == "/index.html" {
            servePage(box, url: url)
            return
        }
        if path.hasPrefix("/api") {
            var query: [String: String] = [:]
            for item in comps?.queryItems ?? [] {
                if let v = item.value { query[item.name] = v }
            }
            let method = task.request.httpMethod ?? "GET"
            DB.queue.async { [weak self] in
                self?.serveApi(box, method: method, path: path, query: query, url: url)
            }
            return
        }
        finish(box, status: 404, data: Data(), mime: "application/json", url: url)
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {
        lock.lock()
        boxes[ObjectIdentifier(task)]?.cancelled = true
        boxes.removeValue(forKey: ObjectIdentifier(task))
        lock.unlock()
    }

    // MARK: - 处理

    private func servePage(_ box: TaskBox, url: URL) {
        guard let data = pageData else {
            finish(box, status: 404, data: Data(), mime: "text/html", url: url)
            return
        }
        finish(box, status: 200, data: data, mime: "text/html", url: url)
    }

    private func serveApi(_ box: TaskBox, method: String, path: String, query: [String: String], url: URL) {
        var body: [String: Any]?
        if let raw = query["_body"] {
            body = (try? JSONSerialization.jsonObject(with: Data(raw.utf8))) as? [String: Any]
        }
        let resp = Api.route(method: method, path: path, query: query, body: body)
        let data: Data
        if let json = resp.json {
            data = (try? JSONSerialization.data(withJSONObject: json, options: [.fragmentsAllowed])) ?? Data("null".utf8)
        } else {
            data = Data("null".utf8)
        }
        finish(box, status: resp.status, data: data, mime: "application/json", url: url)
    }

    private func finish(_ box: TaskBox, status: Int, data: Data, mime: String, url: URL) {
        DispatchQueue.main.async {
            self.lock.lock()
            let cancelled = box.cancelled
            self.lock.unlock()
            guard !cancelled else { return }
            let resp = HTTPURLResponse(
                url: url,
                statusCode: status,
                httpVersion: "HTTP/1.1",
                headerFields: [
                    "Content-Type": mime + "; charset=utf-8",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
                    "Cache-Control": "no-store"
                ]
            )!
            box.task.didReceive(resp)
            box.task.didReceive(data)
            box.task.didFinish()
        }
    }
}
