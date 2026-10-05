package com.hermes.deskbuddy

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Simple battery level helper read from sticky broadcast. */
object BatteryHelper {
    var level: Int = -1
}

class BatteryReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val lvl = intent.getIntExtra("level", -1)
        val scale = intent.getIntExtra("scale", 100)
        BatteryHelper.level = if (scale > 0) (lvl * 100 / scale) else lvl
    }
}
