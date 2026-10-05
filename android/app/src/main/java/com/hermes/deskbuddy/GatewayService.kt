package com.hermes.deskbuddy

import android.app.*
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.gson.JsonObject

/**
 * Foreground service that keeps the WebSocket alive when the app is backgrounded.
 */
class GatewayService : Service() {

    companion object {
        private const val TAG = "GatewayService"
        private const val CHANNEL_ID = "hermes_connection"
        private const val NOTIF_ID = 1
        const val ACTION_STOP = "com.hermes.deskbuddy.STOP"
    }

    private lateinit var client: GatewayClient

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        client = GatewayClient(
            onStateEvent    = { /* handled by MainActivity via LocalBroadcast */ },
            onConnected     = { updateNotification("Connected") },
            onDisconnected  = { updateNotification("Reconnecting…") },
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(NOTIF_ID, buildNotification("Connecting…"))
        client.connect()
        return START_STICKY
    }

    override fun onDestroy() {
        client.disconnect()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        val ch = NotificationChannel(
            CHANNEL_ID, "Hermes Connection",
            NotificationManager.IMPORTANCE_LOW
        ).apply { setShowBadge(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(ch)
    }

    private fun buildNotification(status: String): Notification {
        val pi = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Hermes Desk Buddy")
            .setContentText(status)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(status: String) {
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIF_ID, buildNotification(status))
    }
}
