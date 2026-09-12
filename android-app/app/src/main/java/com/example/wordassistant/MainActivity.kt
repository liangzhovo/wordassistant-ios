package com.example.wordassistant

import android.Manifest
import android.animation.AnimatorSet
import android.animation.ObjectAnimator
import android.app.AlarmManager
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.util.Log
import android.view.Gravity
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.util.Calendar
import java.util.Locale

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private var pythonInstance: com.chaquo.python.Python? = null
    private val handler = Handler(Looper.getMainLooper())
    private var tts: TextToSpeech? = null
    private var exportDataText: String? = null
    private var splashView: FrameLayout? = null

    companion object {
        const val PREFS = "wordassistant_prefs"
        const val ACTION_REMINDER = "com.example.wordassistant.REMINDER"
    }

    // 导出文件（SAF 保存到用户选择的位置）
    private val createDocumentLauncher =
        registerForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
            if (uri != null && exportDataText != null) {
                try {
                    contentResolver.openOutputStream(uri)?.use { it.write(exportDataText!!.toByteArray(Charsets.UTF_8)) }
                    runOnUiThread { webView.evaluateJavascript("showToast('导出成功')", null) }
                } catch (e: Exception) {
                    Log.e("MainActivity", "导出失败", e)
                    runOnUiThread { webView.evaluateJavascript("showToast('导出失败')", null) }
                }
                exportDataText = null
            }
        }

    // 导入文件（SAF 打开文件选择器）
    private val openDocumentLauncher =
        registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
            if (uri != null) {
                try {
                    val text = contentResolver.openInputStream(uri)?.bufferedReader()?.use { it.readText() } ?: ""
                    val quoted = JSONObject.quote(text)
                    runOnUiThread { webView.evaluateJavascript("applyImport($quoted)", null) }
                } catch (e: Exception) {
                    Log.e("MainActivity", "导入失败", e)
                    runOnUiThread { webView.evaluateJavascript("showToast('导入失败')", null) }
                }
            }
        }

    // 通知权限请求（Android 13+）
    private val notifPermLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 初始化Python环境
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        // 根容器：WebView + 启动覆盖层
        val root = FrameLayout(this)
        root.setBackgroundColor(Color.parseColor("#4F46E5"))

        // 设置WebView
        webView = WebView(this)
        webView.setBackgroundColor(Color.parseColor("#F5F7FA"))

        val webSettings: WebSettings = webView.settings
        webSettings.javaScriptEnabled = true
        webSettings.domStorageEnabled = true
        webSettings.databaseEnabled = true

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String?) {
                super.onPageFinished(view, url)
                // 页面加载完成，淡出启动画面
                hideSplash()
            }
        }
        webView.addJavascriptInterface(WebAppInterface(), "Android")

        val webViewParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        )
        root.addView(webView, webViewParams)

        // 初始化 TTS（单词发音）
        tts = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale.US
                tts?.setSpeechRate(0.9f)  // 稍慢，适合学习
            }
        }

        // 创建启动覆盖层（图标 + 标题 + 加载进度）
        val splash = createSplashView()
        splashView = splash
        root.addView(splash, webViewParams)

        setContentView(root)

        startFlaskServer()

        // 启动动画：图标缩放淡入 + 标题上移淡入
        playSplashAnimation(splash)

        handler.postDelayed({
            webView.loadUrl("file:///android_asset/index.html")
        }, 3000)
    }

    /** 创建启动覆盖层：品牌图标 + 应用标题 + 底部加载进度（垂直排列，间距固定） */
    private fun createSplashView(): FrameLayout {
        val splash = FrameLayout(this)
        splash.setBackgroundColor(Color.parseColor("#4F46E5"))

        val content = LinearLayout(this)
        content.orientation = LinearLayout.VERTICAL
        content.gravity = Gravity.CENTER
        content.setPadding(0, 0, 0, 0)

        // 图标
        val icon = ImageView(this)
        icon.setImageResource(R.drawable.ic_launcher)
        icon.scaleType = ImageView.ScaleType.FIT_CENTER
        val iconSize = (110 * resources.displayMetrics.density).toInt()
        content.addView(icon, LinearLayout.LayoutParams(iconSize, iconSize))

        // 标题（图标下方 32dp）
        val title = TextView(this)
        title.text = "🦉 单词助手"
        title.setTextColor(Color.WHITE)
        title.textSize = 24f
        title.gravity = Gravity.CENTER
        val titleParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        titleParams.topMargin = (32 * resources.displayMetrics.density).toInt()
        content.addView(title, titleParams)

        // 进度条（标题下方 72dp，留出明显间距）
        val progressBar = ProgressBar(this)
        progressBar.isIndeterminate = true
        try {
            progressBar.progressTintList = android.content.res.ColorStateList.valueOf(Color.WHITE)
        } catch (e: Exception) {}
        val pbParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
        pbParams.topMargin = (72 * resources.displayMetrics.density).toInt()
        content.addView(progressBar, pbParams)

        splash.addView(content, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ))

        return splash
    }

    /** 播放启动动画：图标缩放淡入 + 标题上移淡入 */
    private fun playSplashAnimation(splash: FrameLayout) {
        val content = splash.getChildAt(0) as? LinearLayout ?: return
        val icon = content.getChildAt(0) as? ImageView ?: return
        val title = content.getChildAt(1) as? TextView ?: return

        // 图标：缩放 0.6→1 + 淡入
        icon.scaleX = 0.6f
        icon.scaleY = 0.6f
        icon.alpha = 0f
        val iconAlpha = ObjectAnimator.ofFloat(icon, "alpha", 0f, 1f).apply { duration = 700 }
        val iconScaleX = ObjectAnimator.ofFloat(icon, "scaleX", 0.6f, 1f).apply { duration = 700 }
        val iconScaleY = ObjectAnimator.ofFloat(icon, "scaleY", 0.6f, 1f).apply { duration = 700 }

        // 标题：上移淡入（延迟 300ms）
        title.alpha = 0f
        title.translationY = 30f * resources.displayMetrics.density
        val titleAlpha = ObjectAnimator.ofFloat(title, "alpha", 0f, 1f).apply {
            duration = 600
            startDelay = 300
        }
        val titleTranslate = ObjectAnimator.ofFloat(title, "translationY", 30f * resources.displayMetrics.density, 0f).apply {
            duration = 600
            startDelay = 300
        }

        val set = AnimatorSet()
        set.playTogether(iconAlpha, iconScaleX, iconScaleY, titleAlpha, titleTranslate)
        set.interpolator = android.view.animation.DecelerateInterpolator()
        set.start()
    }

    /** 淡出启动画面 */
    private fun hideSplash() {
        val splash = splashView ?: return
        if (splash.visibility != View.VISIBLE) return
        splash.animate().alpha(0f).setDuration(600).withEndAction {
            splash.visibility = View.GONE
            // 确保状态栏颜色已切换到应用界面配色
            webView.evaluateJavascript("if(typeof applyTheme==='function')applyTheme()", null)
        }.start()
        // 兜底：无论如何 6 秒后强制隐藏
        handler.postDelayed({
            if (splash.visibility == View.VISIBLE) {
                splash.alpha = 0f
                splash.visibility = View.GONE
            }
        }, 6000)
    }

    /** 进入应用界面后，状态栏改为浅色背景 + 深色文字 */
    private fun applyLightStatusBar() {
        try {
            window.statusBarColor = Color.parseColor("#F5F7FA")
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "状态栏切换失败", e)
        }
    }

    private fun startFlaskServer() {
        Thread {
            try {
                val dbFile = java.io.File(filesDir, "简明英汉字典增强版.db")
                if (!dbFile.exists()) {
                    assets.open("简明英汉字典增强版.db").use { input ->
                        dbFile.outputStream().use { output ->
                            input.copyTo(output)
                        }
                    }
                }

                val pythonModule = Python.getInstance().getModule("app")
                pythonModule.callAttr("set_db_path", dbFile.absolutePath)
                pythonModule.callAttr("main")
            } catch (e: Exception) {
                Log.e("MainActivity", "启动Flask服务器失败: ${e.message}")
            }
        }.start()
    }

    // 每日提醒调度（AlarmManager，每天准点）
    private fun scheduleReminderInternal(hour: Int, minute: Int, enabled: Boolean) {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        prefs.edit()
            .putBoolean("reminder_enabled", enabled)
            .putInt("reminder_hour", hour)
            .putInt("reminder_minute", minute)
            .apply()

        val alarmManager = getSystemService(ALARM_SERVICE) as AlarmManager
        val intent = Intent(this, ReminderReceiver::class.java).setAction(ACTION_REMINDER)
        val pendingIntent = PendingIntent.getBroadcast(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        if (!enabled) {
            alarmManager.cancel(pendingIntent)
            return
        }

        val cal = Calendar.getInstance()
        cal.set(Calendar.HOUR_OF_DAY, hour)
        cal.set(Calendar.MINUTE, minute)
        cal.set(Calendar.SECOND, 0)
        cal.set(Calendar.MILLISECOND, 0)
        if (cal.timeInMillis <= System.currentTimeMillis()) {
            cal.add(Calendar.DAY_OF_YEAR, 1)
        }
        alarmManager.setInexactRepeating(AlarmManager.RTC_WAKEUP, cal.timeInMillis, AlarmManager.INTERVAL_DAY, pendingIntent)
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        pythonInstance = null
        tts?.stop()
        tts?.shutdown()
        webView.destroy()
        super.onDestroy()
    }

    // 系统主题切换时，通知 JS 重新应用主题
    override fun onConfigurationChanged(newConfig: android.content.res.Configuration) {
        super.onConfigurationChanged(newConfig)
        try {
            webView.evaluateJavascript("if(typeof applyTheme==='function')applyTheme()", null)
        } catch (e: Exception) {}
    }

    /**
     * JavaScript接口，用于WebView和Android应用之间的通信
     */
    inner class WebAppInterface {
        @JavascriptInterface
        fun getApiUrl(): String {
            return "http://127.0.0.1:5000"
        }

        @JavascriptInterface
        fun openUrl(url: String) {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            startActivity(intent)
        }

        @JavascriptInterface
        fun showToast(message: String) {
            Log.d("WebAppInterface", "Toast: $message")
        }

        // 设置状态栏颜色（跟随应用主题，解决深色模式下状态栏不统一问题）
        @JavascriptInterface
        fun setStatusBarColor(color: String) {
            runOnUiThread {
                try {
                    val colorInt = Color.parseColor(color)
                    window.statusBarColor = colorInt
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                        val luminance = (0.299 * Color.red(colorInt) + 0.587 * Color.green(colorInt) + 0.114 * Color.blue(colorInt)).toInt()
                        if (luminance < 128) {
                            window.decorView.systemUiVisibility = 0
                        } else {
                            window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
                        }
                    }
                } catch (e: Exception) {
                    Log.e("MainActivity", "状态栏颜色设置失败", e)
                }
            }
        }

        // 获取系统是否深色模式（比 WebView matchMedia 可靠）
        @JavascriptInterface
        fun isSystemDarkMode(): Boolean {
            val nightModeFlags = resources.configuration.uiMode and android.content.res.Configuration.UI_MODE_NIGHT_MASK
            return nightModeFlags == android.content.res.Configuration.UI_MODE_NIGHT_YES
        }

        // 单词发音（TTS）
        @JavascriptInterface
        fun speak(word: String) {
            runOnUiThread {
                try {
                    tts?.stop()
                    tts?.speak(word, TextToSpeech.QUEUE_FLUSH, null, "word_${System.currentTimeMillis()}")
                } catch (e: Exception) {
                    Log.e("MainActivity", "TTS 发音失败", e)
                }
            }
        }

        // 导出单词本（SAF 让用户选择保存位置）
        @JavascriptInterface
        fun exportData(json: String) {
            exportDataText = json
            runOnUiThread {
                try {
                    createDocumentLauncher.launch("wordassistant-backup-${System.currentTimeMillis()}.json")
                } catch (e: Exception) {
                    Log.e("MainActivity", "导出启动失败", e)
                    exportDataText = null
                }
            }
        }

        // 导入单词本（SAF 打开文件选择器）
        @JavascriptInterface
        fun pickImport() {
            runOnUiThread {
                try {
                    openDocumentLauncher.launch(arrayOf("application/json", "text/plain", "application/octet-stream", "*/*"))
                } catch (e: Exception) {
                    Log.e("MainActivity", "导入启动失败", e)
                }
            }
        }

        // 每日学习提醒
        @JavascriptInterface
        fun scheduleReminder(hour: Int, minute: Int, enabled: Boolean) {
            runOnUiThread {
                if (enabled && Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    if (ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                        notifPermLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                }
                scheduleReminderInternal(hour, minute, enabled)
            }
        }
    }
}

/**
 * 每日提醒接收器：发通知，并在开机后重新调度
 */
class ReminderReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return

        // 开机后重新调度提醒
        if (action == Intent.ACTION_BOOT_COMPLETED) {
            val prefs = context.getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE)
            if (prefs.getBoolean("reminder_enabled", false)) {
                val hour = prefs.getInt("reminder_hour", 9)
                val minute = prefs.getInt("reminder_minute", 0)
                val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
                val i = Intent(context, ReminderReceiver::class.java).setAction(MainActivity.ACTION_REMINDER)
                val pi = PendingIntent.getBroadcast(
                    context, 0, i,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                val cal = Calendar.getInstance()
                cal.set(Calendar.HOUR_OF_DAY, hour)
                cal.set(Calendar.MINUTE, minute)
                cal.set(Calendar.SECOND, 0)
                cal.set(Calendar.MILLISECOND, 0)
                if (cal.timeInMillis <= System.currentTimeMillis()) cal.add(Calendar.DAY_OF_YEAR, 1)
                alarmManager.setInexactRepeating(AlarmManager.RTC_WAKEUP, cal.timeInMillis, AlarmManager.INTERVAL_DAY, pi)
            }
            return
        }

        // 到点发通知
        if (action == MainActivity.ACTION_REMINDER) {
            val channelId = "wordassistant_reminder"
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val channel = NotificationChannel(channelId, "每日学习提醒", NotificationManager.IMPORTANCE_HIGH)
                channel.description = "每天定时提醒背单词"
                (context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
            }

            val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                Notification.Builder(context, channelId)
            } else {
                @Suppress("DEPRECATION")
                Notification.Builder(context)
            }
            val notification = builder
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle("🦉 该背单词啦")
                .setContentText("今日单词任务在等你，坚持打卡！")
                .setAutoCancel(true)
                .build()

            val hasPermission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
            } else true

            if (hasPermission) {
                (context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).notify(1, notification)
            }
        }
    }
}
