package com.ccmonitor.cc_monitor_app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    companion object {
        private const val CHANNEL = "cc_monitor/notifications"
        private const val TAG = "cc-monitor:main"
        private const val REQUEST_NOTIFICATION_PERMISSION = 1001
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        NotificationHelper.createChannels(this)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        val channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
        NotificationForegroundService.setFlutterChannel(channel)

        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "requestPermission" -> {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        if (ContextCompat.checkSelfPermission(
                                this, Manifest.permission.POST_NOTIFICATIONS
                            ) == PackageManager.PERMISSION_GRANTED
                        ) {
                            result.success(true)
                        } else {
                            ActivityCompat.requestPermissions(
                                this,
                                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                                REQUEST_NOTIFICATION_PERMISSION
                            )
                            result.success(false)
                        }
                    } else {
                        result.success(true)
                    }
                }

                "startService" -> {
                    Log.d(TAG, "startService called")
                    val intent = Intent(this, NotificationForegroundService::class.java)
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        startForegroundService(intent)
                    } else {
                        startService(intent)
                    }
                    result.success(true)
                }

                "stopService" -> {
                    Log.d(TAG, "stopService called")
                    stopService(Intent(this, NotificationForegroundService::class.java))
                    result.success(true)
                }

                "updateSticky" -> {
                    val working = call.argument<Int>("working") ?: 0
                    val approval = call.argument<Int>("approval") ?: 0
                    val completed = call.argument<Int>("completed") ?: 0
                    val serverLabel = call.argument<String>("serverLabel") ?: ""
                    NotificationForegroundService.updateNotification(
                        working, approval, completed, serverLabel
                    )
                    result.success(true)
                }

                "showAlert" -> {
                    val sessionName = call.argument<String>("sessionName") ?: ""
                    val state = call.argument<String>("state") ?: ""
                    NotificationForegroundService.fireAlert(sessionName, state)
                    result.success(true)
                }

                "updateSettings" -> {
                    val sound = call.argument<Boolean>("sound") ?: true
                    val vibrate = call.argument<Boolean>("vibrate") ?: true
                    NotificationForegroundService.updateSettings(sound, vibrate)
                    result.success(true)
                }

                else -> result.notImplemented()
            }
        }
    }
}
