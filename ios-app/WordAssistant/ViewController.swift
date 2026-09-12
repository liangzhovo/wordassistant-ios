import UIKit
import WebKit
import UniformTypeIdentifiers

/// 注入前端的 JS：模拟 Android 桥接接口 + 安全区样式
enum JS {
    /// 模拟 window.Android（前端 index.html 直接使用该接口）
    static let shim = """
    (function(){
      if (window.Android) return;
      window.Android = {
        getApiUrl: function(){ return 'wordapp://localhost'; },
        openUrl: function(url){ window.webkit.messageHandlers.bridge.postMessage({type:'openUrl', url:String(url)}); },
        showToast: function(msg){ window.webkit.messageHandlers.bridge.postMessage({type:'toast', msg:String(msg)}); },
        setStatusBarColor: function(color){ window.webkit.messageHandlers.bridge.postMessage({type:'statusBarColor', color:String(color)}); },
        isSystemDarkMode: function(){ return window.matchMedia('(prefers-color-scheme: dark)').matches; },
        speak: function(word){ window.webkit.messageHandlers.bridge.postMessage({type:'speak', word:String(word)}); },
        exportData: function(json){ window.webkit.messageHandlers.bridge.postMessage({type:'export', json:String(json)}); },
        pickImport: function(){ window.webkit.messageHandlers.bridge.postMessage({type:'import'}); },
        scheduleReminder: function(h, m, enabled){ window.webkit.messageHandlers.bridge.postMessage({type:'reminder', hour:h, minute:m, enabled:!!enabled}); }
      };
    })();
    """

    /// 刘海/底部安全区适配
    static let safeAreaCSS = """
    (function(){
      function patch(){
        if(!document.head) return;
        var st = document.createElement('style');
        st.textContent = 'header{padding-top:calc(16px + env(safe-area-inset-top)) !important;} .container{padding-bottom:calc(96px + env(safe-area-inset-bottom)) !important;}';
        document.head.appendChild(st);
      }
      if(document.readyState === 'loading'){ document.addEventListener('DOMContentLoaded', patch); } else { patch(); }
    })();
    """
}

final class ViewController: UIViewController, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, UIDocumentPickerDelegate {

    private var webView: WKWebView!
    private var schemeHandler: SchemeHandler!
    private let speech = Speech()
    private let reminder = Reminder()
    private var pendingExportJSON: String?
    private var statusBarDark = false
    private var splashView: UIView?
    private var toastLabel: UILabel?

    override var preferredStatusBarStyle: UIStatusBarStyle {
        statusBarDark ? .darkContent : .lightContent
    }

    // MARK: - 生命周期

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 0.31, green: 0.27, blue: 0.90, alpha: 1)

        let config = WKWebViewConfiguration()
        schemeHandler = SchemeHandler()
        config.setURLSchemeHandler(schemeHandler, forURLScheme: "wordapp")
        let uc = config.userContentController
        uc.add(self, name: "bridge")
        uc.addUserScript(WKUserScript(source: JS.shim, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        uc.addUserScript(WKUserScript(source: JS.safeAreaCSS, injectionTime: .atDocumentStart, forMainFrameOnly: true))

        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(webView)
        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: view.topAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor)
        ])

        showSplash("正在初始化词典…")

        DB.queue.async { [weak self] in
            do {
                try DB.bootstrap()
            } catch {
                print("数据库初始化失败: \(error)")
            }
            DispatchQueue.main.async {
                self?.hideSplash()
                let url = URL(string: "wordapp://localhost/index.html")!
                self?.webView.load(URLRequest(url: url))
            }
        }
    }

    // MARK: - 启动画面

    private func showSplash(_ text: String) {
        let container = UIView(frame: view.bounds)
        container.backgroundColor = UIColor(red: 0.31, green: 0.27, blue: 0.90, alpha: 1)
        let spinner = UIActivityIndicatorView(style: .large)
        spinner.color = .white
        spinner.startAnimating()
        let label = UILabel()
        label.text = text
        label.textColor = .white
        label.font = .systemFont(ofSize: 15)
        let stack = UIStackView(arrangedSubviews: [spinner, label])
        stack.axis = .vertical
        stack.spacing = 14
        stack.alignment = .center
        stack.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: container.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: container.centerYAnchor)
        ])
        view.addSubview(container)
        splashView = container
    }

    private func hideSplash() {
        UIView.animate(withDuration: 0.35, animations: {
            self.splashView?.alpha = 0
        }) { _ in
            self.splashView?.removeFromSuperview()
            self.splashView = nil
        }
    }

    // MARK: - JS 桥接

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let type = body["type"] as? String else { return }
        switch type {
        case "speak":
            if let w = body["word"] as? String { speech.speak(w) }
        case "openUrl":
            if let u = body["url"] as? String, let url = URL(string: u) {
                UIApplication.shared.open(url)
            }
        case "toast":
            if let m = body["msg"] as? String { showToast(m) }
        case "statusBarColor":
            if let c = body["color"] as? String { applyStatusBarColor(c) }
        case "export":
            if let j = body["json"] as? String { exportJSON(j) }
        case "import":
            pickImportFile()
        case "reminder":
            let h = body["hour"] as? Int ?? 9
            let m = body["minute"] as? Int ?? 0
            let enabled = body["enabled"] as? Bool ?? false
            reminder.schedule(hour: h, minute: m, enabled: enabled)
        default:
            break
        }
    }

    // MARK: - 状态栏

    private func applyStatusBarColor(_ hex: String) {
        let clean = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard clean.count >= 6, let v = UInt64(clean.prefix(6), radix: 16) else { return }
        let r = Double((v >> 16) & 0xFF) / 255.0
        let g = Double((v >> 8) & 0xFF) / 255.0
        let b = Double(v & 0xFF) / 255.0
        let luminance = 0.299 * r + 0.587 * g + 0.114 * b
        statusBarDark = luminance >= 0.5
        setNeedsStatusBarAppearanceUpdate()
    }

    // MARK: - Toast

    private func showToast(_ text: String) {
        toastLabel?.removeFromSuperview()
        let label = UILabel()
        label.text = text
        label.textColor = .white
        label.backgroundColor = UIColor(white: 0.1, alpha: 0.88)
        label.font = .systemFont(ofSize: 14)
        label.textAlignment = .center
        label.numberOfLines = 0
        label.layer.cornerRadius = 10
        label.layer.masksToBounds = true
        label.alpha = 0
        label.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -40),
            label.widthAnchor.constraint(lessThanOrEqualToConstant: 280)
        ])
        label.layoutIfNeeded()
        toastLabel = label
        UIView.animate(withDuration: 0.25, animations: { label.alpha = 1 }) { _ in
            UIView.animate(withDuration: 0.3, delay: 1.6, options: [], animations: {
                label.alpha = 0
            }) { _ in
                label.removeFromSuperview()
                if self.toastLabel === label { self.toastLabel = nil }
            }
        }
    }

    // MARK: - 导出 / 导入（对应 Android SAF）

    private func exportJSON(_ json: String) {
        let fm = FileManager.default
        let temp = fm.temporaryDirectory.appendingPathComponent("wordassistant-backup-\(Int(Date().timeIntervalSince1970)).json")
        do {
            try json.write(to: temp, atomically: true, encoding: .utf8)
            let picker = UIDocumentPickerViewController(forExporting: [temp])
            picker.delegate = self
            present(picker, animated: true)
        } catch {
            showToast("导出失败")
        }
    }

    private func pickImportFile() {
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.json, .plainText, .text, .data])
        picker.delegate = self
        present(picker, animated: true)
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        guard let url = urls.first else { return }
        do {
            let text = try String(contentsOf: url, encoding: .utf8)
            let data = try JSONSerialization.data(withJSONObject: text)
            let quoted = String(data: data, encoding: .utf8) ?? "\"\""
            webView.evaluateJavaScript("applyImport(\(quoted))") { _, error in
                if error != nil {
                    self.showToast("导入失败")
                }
            }
        } catch {
            showToast("导入失败")
        }
    }

    // MARK: - WKNavigationDelegate

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        print("页面加载失败: \(error)")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        print("页面预加载失败: \(error)")
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.navigationType == .linkActivated,
           let url = navigationAction.request.url,
           url.scheme != "wordapp" {
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }
}
