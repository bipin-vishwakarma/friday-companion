package com.hermes.deskbuddy

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Stores gateway URL and auth token in encrypted shared prefs.
 * Falls back to plaintext prefs on API 26 if crypto init fails.
 */
object Config {

    private const val PREF_FILE = "desk_buddy_config"
    private const val KEY_GATEWAY_URL = "gateway_url"
    private const val KEY_AUTH_TOKEN  = "auth_token"
    private const val KEY_PC_MAC      = "pc_mac"
    private const val KEY_PC_BROADCAST = "pc_broadcast"
    private const val KEY_DEVICE_NAME = "device_name"

    // Defaults matching the PC-side gateway
    private const val DEFAULT_GATEWAY_URL  = "ws://192.168.1.11:8765/ws"
    private const val DEFAULT_AUTH_TOKEN   = "_dxFFVlMs9yCjR-EPZck3H9ywJ59smWbRAz_vLjXtAY"
    private const val DEFAULT_PC_MAC       = "00:45:E2:83:14:13"
    private const val DEFAULT_PC_BROADCAST = "192.168.1.255"
    private const val DEFAULT_DEVICE_NAME  = "SM-J260GU"

    @Volatile private var prefs: SharedPreferences? = null

    fun init(context: Context) {
        prefs = try {
            val master = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                context, PREF_FILE, master,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        } catch (e: Exception) {
            // Fallback on devices where keystore is unavailable
            context.getSharedPreferences(PREF_FILE, Context.MODE_PRIVATE)
        }
    }

    private fun p() = prefs ?: throw IllegalStateException("Config.init() not called")

    var gatewayUrl: String
        get() = p().getString(KEY_GATEWAY_URL, DEFAULT_GATEWAY_URL)!!
        set(v) = p().edit().putString(KEY_GATEWAY_URL, v).apply()

    var authToken: String
        get() = p().getString(KEY_AUTH_TOKEN, DEFAULT_AUTH_TOKEN)!!
        set(v) = p().edit().putString(KEY_AUTH_TOKEN, v).apply()

    var pcMac: String
        get() = p().getString(KEY_PC_MAC, DEFAULT_PC_MAC)!!
        set(v) = p().edit().putString(KEY_PC_MAC, v).apply()

    var pcBroadcast: String
        get() = p().getString(KEY_PC_BROADCAST, DEFAULT_PC_BROADCAST)!!
        set(v) = p().edit().putString(KEY_PC_BROADCAST, v).apply()

    var deviceName: String
        get() = p().getString(KEY_DEVICE_NAME, DEFAULT_DEVICE_NAME)!!
        set(v) = p().edit().putString(KEY_DEVICE_NAME, v).apply()

    /** WebSocket URL with token baked into query string */
    fun wsUrl(): String {
        val base = gatewayUrl.trimEnd('/')
        return "$base?token=${authToken}"
    }

    /** HTTP base for REST calls */
    fun httpBase(): String {
        return gatewayUrl
            .replace("ws://", "http://")
            .replace("wss://", "https://")
            .removeSuffix("/ws")
            .removeSuffix("/ws?token=${authToken}")
            .trimEnd('/')
    }
}
