package dev.mirmik.grim

import android.os.Bundle
import android.net.Uri
import android.view.View
import android.webkit.WebView
import android.webkit.CookieManager
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

class MainActivity : TauriActivity() {
  override fun onPause() {
    CookieManager.getInstance().flush()
    super.onPause()
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
  }

  override fun onWebViewCreate(webView: WebView) {
    super.onWebViewCreate(webView)
    // Keep both orientations clear of status/navigation bars and display cutouts.
    val content = findViewById<View>(android.R.id.content)
    ViewCompat.setOnApplyWindowInsetsListener(content) { view, insets ->
      val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
      view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
      WindowInsetsCompat.CONSUMED
    }
    ViewCompat.requestApplyInsets(content)
    onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
      override fun handleOnBackPressed() {
        // The reader closes its panel/TOC first, then returns to the library.
        // At the library, finish the activity instead of replaying iframe history.
        webView.evaluateJavascript("window.dispatchEvent(new Event('grim-back', {cancelable:true}))") { unhandled ->
          if (unhandled != "false") {
            val url = Uri.parse(webView.url ?: "")
            if (url.host != "tauri.localhost" && url.scheme in listOf("http", "https")) {
              // A server library (or its network error page) returns to the
              // bundled start screen, where the saved address can be changed.
              webView.stopLoading()
              webView.loadUrl("http://tauri.localhost/")
            } else finish()
          }
        }
      }
    })
  }
}
