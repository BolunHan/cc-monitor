package com.ccmonitor.cc_monitor_app

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import io.flutter.plugin.common.MethodChannel

class NotificationForegroundService : Service() {

    companion object {
        private const val TAG = "cc-monitor:fgservice"
        private var instance: NotificationForegroundService? = null
        private var flutterChannel: MethodChannel? = null

        private var cachedWorking = 0
        private var cachedApproval = 0
        private var cachedCompleted = 0
        private var cachedServerLabel = ""

        fun setFlutterChannel(channel: MethodChannel) {
            flutterChannel = channel
        }

        fun updateNotification(
            working: Int,
            approval: Int,
            completed: Int,
            serverLabel: String
        ) {
            cachedWorking = working
            cachedApproval = approval
            cachedCompleted = completed
            cachedServerLabel = serverLabel
            instance?.refreshNotification()
        }

        fun fireAlert(sessionName: String, state: String) {
            instance?.let { svc ->
                NotificationHelper.showAlert(svc, sessionName, state)
            }
        }

        fun updateSettings(sound: Boolean, vibrate: Boolean) {
            NotificationHelper.updateSoundVibrate(sound, vibrate)
        }
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        Log.d(TAG, "Service created")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action
        Log.d(TAG, "onStartCommand action=$action")

        when (action) {
            NotificationHelper.ACTION_WORKING,
            NotificationHelper.ACTION_APPROVAL,
            NotificationHelper.ACTION_COMPLETED -> {
                flutterChannel?.invokeMethod("onActionTap", action)
            }
        }

        refreshNotification()
        return START_STICKY
    }

    fun refreshNotification() {
        val notification = NotificationHelper.buildOngoingNotification(
            this,
            cachedWorking,
            cachedApproval,
            cachedCompleted,
            cachedServerLabel
        )
        startForeground(NotificationHelper.NOTIFY_ONGOING_ID, notification)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        instance = null
        Log.d(TAG, "Service destroyed")
        super.onDestroy()
    }
}
