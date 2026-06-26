package com.example.twinkstar

import android.annotation.SuppressLint
import android.os.Bundle
import android.util.Log
import android.view.View
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread
import android.webkit.ConsoleMessage
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import com.example.twinkstar.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var webView: WebView

    // 预加载的本地数据
    private var orbitErrorData: String? = null
    private var tecTreesData: String? = null
    private var eofMapsData: String? = null
    private var tecMeanData: String? = null
    @Volatile private var qianfanTLE: String? = null

    /**
     * JavaScript 桥接接口
     * JS 端通过 AndroidBridge.getXxx() 获取数据
     */
    inner class AndroidBridge {
        @JavascriptInterface
        fun getOrbitErrorData(): String? {
            Log.i("TwinkStar", "JS 调用 getOrbitErrorData(), 数据大小: ${orbitErrorData?.length ?: 0}")
            return orbitErrorData
        }

        @JavascriptInterface
        fun getTecTreesData(): String? {
            Log.i("TwinkStar", "JS 调用 getTecTreesData(), 数据大小: ${tecTreesData?.length ?: 0}")
            return tecTreesData
        }

        @JavascriptInterface
        fun getEofMapsData(): String? {
            Log.i("TwinkStar", "JS 调用 getEofMapsData(), 数据大小: ${eofMapsData?.length ?: 0}")
            return eofMapsData
        }

        @JavascriptInterface
        fun getTecMeanData(): String? {
            Log.i("TwinkStar", "JS 调用 getTecMeanData(), 数据大小: ${tecMeanData?.length ?: 0}")
            return tecMeanData
        }

        @JavascriptInterface
        fun getQianfanTLE(): String? {
            Log.i("TwinkStar", "JS 调用 getQianfanTLE(), 数据大小: ${qianfanTLE?.length ?: 0}")
            return qianfanTLE
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 全屏沉浸模式
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // 预加载 assets 数据
        preloadAssets()

        webView = binding.webview

        // WebView 配置
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            allowUniversalAccessFromFileURLs = true  // 允许 fetch() 访问 file:// URL
            mediaPlaybackRequiresUserGesture = false
        }
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)

        // 注册 JavaScript 桥接接口
        webView.addJavascriptInterface(AndroidBridge(), "AndroidBridge")

        // 日志输出
        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(msg: ConsoleMessage?): Boolean {
                msg?.let {
                    Log.d("WebView", "${it.messageLevel()}: ${it.message()}")
                }
                return true
            }
        }

        webView.webViewClient = object : WebViewClient() {}

        webView.loadUrl("file:///android_asset/3DNavigation_error.html")
    }

    private fun preloadAssets() {
        loadAsset("orbit_error_3d_data.json") { orbitErrorData = it }
        loadAsset("tec_trees.json") { tecTreesData = it }
        loadAsset("eof_maps.json") { eofMapsData = it }
        loadAsset("tec_mean.json") { tecMeanData = it }
        fetchQianfanTLE()
    }

    // 多个 TLE 数据源，按优先级排列
    // 1. GitHub raw: 由 Actions 从 Space-Track.org 自动同步（推荐，国内可访问）
    // 2. celestrak.org: 官方原版
    // 3. celestrak.com: 旧域名备用
    private val tleSources = listOf(
        // 由 .github/workflows/sync-qianfan-tle.yml 自动同步，改 YOUR_USER 为你的 GitHub 用户名
        "https://raw.githubusercontent.com/ZISHENGZHAO2/3Dearth/main/app/src/main/assets/qianfan_tle_backup.txt",
        "https://celestrak.org/NORAD/elements/gp.php?NAME=QIANFAN&FORMAT=tle",
        "https://www.celestrak.com/NORAD/elements/gp.php?NAME=QIANFAN&FORMAT=tle"
    )

    private fun fetchQianfanTLE() {
        thread(start = true) {
            var lastError: Exception? = null

            // 依次尝试所有数据源
            for (source in tleSources) {
                try {
                    Log.i("TwinkStar", "尝试获取 TLE: $source")
                    val url = URL(source)
                    val conn = url.openConnection() as HttpURLConnection
                    conn.setRequestProperty("User-Agent", "TwinkStar/1.0")
                    conn.connectTimeout = 10000
                    conn.readTimeout = 10000
                    if (conn.responseCode == 200) {
                        val data = conn.inputStream.bufferedReader().use { it.readText() }
                        if (data.isNotBlank() && data.startsWith("QIANFAN")) {
                            qianfanTLE = data
                            Log.i("TwinkStar", "千帆星座 TLE 获取成功: ${data.length} 字符")
                            conn.disconnect()
                            return@thread
                        }
                    }
                    conn.disconnect()
                } catch (e: Exception) {
                    lastError = e
                    Log.w("TwinkStar", "TLE 源 [$source] 失败: ${e.message}")
                }
            }

            // 所有网络源都失败，尝试从 assets 加载备用数据
            try {
                val backup = assets.open("qianfan_tle_backup.txt")
                    .bufferedReader().use { it.readText() }
                if (backup.isNotBlank() && backup.startsWith("QIANFAN")) {
                    qianfanTLE = backup
                    Log.i("TwinkStar", "使用离线 TLE 备用数据: ${backup.length} 字符")
                    return@thread
                }
            } catch (e: Exception) {
                Log.e("TwinkStar", "离线 TLE 备用数据加载失败", e)
            }

            Log.e("TwinkStar", "千帆星座 TLE 所有数据源均获取失败", lastError)
        }
    }

    private fun loadAsset(filename: String, setter: (String) -> Unit) {
        try {
            val data = assets.open(filename).bufferedReader().use { it.readText() }
            setter(data)
            Log.i("TwinkStar", "预加载 $filename: ${data.length} 字符")
        } catch (e: Exception) {
            Log.e("TwinkStar", "加载 $filename 失败", e)
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
    }

    override fun onPause() {
        super.onPause()
        webView.onPause()
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }
}