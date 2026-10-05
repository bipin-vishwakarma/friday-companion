package com.hermes.deskbuddy

import android.os.Handler
import android.os.Looper
import android.util.Log
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import okhttp3.*
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Persistent WebSocket client with exponential-backoff reconnect.
 * Never crashes the app on disconnect — just keeps trying.
 */
class GatewayClient(
    private val onStateEvent: (JsonObject) -> Unit,
    private val onConnected: () -> Unit,
    private val onDisconnected: () -> Unit,
) {
    companion object {
        private const val TAG = "GatewayClient"
        private const val MAX_BACKOFF_MS = 30_000L
        private const val INITIAL_BACKOFF_MS = 1_000L
    }

    private val http = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)   // keep alive forever
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private val mainHandler = Handler(Looper.getMainLooper())
    private var ws: WebSocket? = null
    private var backoffMs = INITIAL_BACKOFF_MS
    private val running = AtomicBoolean(false)
    private var reconnectRunnable: Runnable? = null

    // ── Public API ───────────────────────────────────────────────────

    fun connect() {
        running.set(true)
        backoffMs = INITIAL_BACKOFF_MS
        attemptConnect()
    }

    fun disconnect() {
        running.set(false)
        reconnectRunnable?.let { mainHandler.removeCallbacks(it) }
        ws?.close(1000, "App stopped")
        ws = null
    }

    fun send(type: String, payload: Map<String, Any?> = emptyMap()) {
        val obj = mutableMapOf<String, Any?>("type" to type)
        obj.putAll(payload)
        val json = gson.toJson(obj)
        val sent = ws?.send(json) ?: false
        if (!sent) Log.w(TAG, "send failed (disconnected?): $type")
    }

    fun sendCommand(command: String, extras: Map<String, Any?> = emptyMap()) {
        send("command", mapOf("command" to command) + extras)
    }

    // ── Internal ─────────────────────────────────────────────────────

    private fun attemptConnect() {
        if (!running.get()) return
        val url = Config.wsUrl()
        Log.i(TAG, "Connecting to $url (backoff=${backoffMs}ms)")

        val request = Request.Builder().url(url).build()
        ws = http.newWebSocket(request, object : WebSocketListener() {

            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "Connected")
                backoffMs = INITIAL_BACKOFF_MS
                // Announce ourselves
                send("device_info", mapOf(
                    "device_name" to Config.deviceName,
                    "app_version" to "0.1.0",
                    "battery"     to BatteryHelper.level,
                    "wifi_rssi"   to 0,
                ))
                mainHandler.post { onConnected() }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val obj = JsonParser.parseString(text).asJsonObject
                    mainHandler.post { onStateEvent(obj) }
                } catch (e: Exception) {
                    Log.e(TAG, "Parse error: $text", e)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w(TAG, "Connection failed: ${t.message}")
                mainHandler.post { onDisconnected() }
                scheduleReconnect()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "Closed: $code $reason")
                if (running.get()) {
                    mainHandler.post { onDisconnected() }
                    scheduleReconnect()
                }
            }
        })
    }

    private fun scheduleReconnect() {
        if (!running.get()) return
        reconnectRunnable?.let { mainHandler.removeCallbacks(it) }
        Log.i(TAG, "Reconnecting in ${backoffMs}ms")
        val r = Runnable { attemptConnect() }
        reconnectRunnable = r
        mainHandler.postDelayed(r, backoffMs)
        backoffMs = (backoffMs * 2).coerceAtMost(MAX_BACKOFF_MS)
    }
}
