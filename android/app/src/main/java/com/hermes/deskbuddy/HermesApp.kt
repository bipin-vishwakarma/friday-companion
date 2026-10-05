package com.hermes.deskbuddy

import android.app.Application

class HermesApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Config.init(this)
    }
}
