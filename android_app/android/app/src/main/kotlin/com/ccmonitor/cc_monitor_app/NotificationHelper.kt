package com.ccmonitor.cc_monitor_app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import android.widget.RemoteViews
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat

object NotificationHelper {

    const val CHANNEL_ONGOING = "cc_monitor_ongoing"
    const val CHANNEL_ALERT = "cc_monitor_alerts"
    const val NOTIFY_ONGOING_ID = 1

    const val ACTION_WORKING = "cc_monitor.action.WORKING"
    const val ACTION_APPROVAL = "cc_monitor.action.APPROVAL"
    const val ACTION_COMPLETED = "cc_monitor.action.COMPLETED"

    private var soundEnabled = true
    private var vibrateEnabled = true

    fun createChannels(context: Context) {
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        // Ongoing channel — HIGH importance for lock screen visibility, no sound
        val ongoingChannel = NotificationChannel(
            CHANNEL_ONGOING,
            "Session Monitor",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "Ongoing session status"
            setSound(null, null)
            enableVibration(false)
            setShowBadge(false)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
        }
        nm.createNotificationChannel(ongoingChannel)

        // Alert channel — created with current sound/vibrate settings
        createAlertChannel(nm)
    }

    private fun createAlertChannel(nm: NotificationManager) {
        // Delete old channel so new settings take effect
        nm.deleteNotificationChannel(CHANNEL_ALERT)

        val channel = NotificationChannel(
            CHANNEL_ALERT,
            "Session Alerts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "State transition alerts"
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            setShowBadge(true)

            if (soundEnabled) {
                val attrs = AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
                setSound(
                    RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
                    attrs
                )
            } else {
                setSound(null, null)
            }

            if (vibrateEnabled) {
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 200, 100, 200)
            } else {
                enableVibration(false)
                vibrationPattern = null
            }
        }
        nm.createNotificationChannel(channel)
    }

    fun updateSoundVibrate(context: Context, sound: Boolean, vibrate: Boolean) {
        soundEnabled = sound
        vibrateEnabled = vibrate
        val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        createAlertChannel(nm)
    }

    fun buildOngoingNotification(
        context: Context,
        working: Int,
        approval: Int,
        completed: Int,
        serverLabel: String
    ): Notification {
        val remoteViews = RemoteViews(context.packageName, R.layout.notification_ongoing)

        val title = buildTitle(working, approval, completed)
        remoteViews.setTextViewText(R.id.notify_title, title)
        remoteViews.setTextViewText(
            R.id.notify_subtitle,
            if (serverLabel.isNotEmpty()) "Connected to: $serverLabel" else "No server connected"
        )

        // Working button
        remoteViews.setTextViewText(R.id.btn_working, "$working working")
        remoteViews.setFloat(R.id.btn_working, "setAlpha", if (working > 0) 1.0f else 0.4f)
        remoteViews.setOnClickPendingIntent(
            R.id.btn_working,
            buildActionPendingIntent(context, ACTION_WORKING, 100)
        )

        // Approval button
        remoteViews.setTextViewText(R.id.btn_approval, "$approval pending")
        remoteViews.setFloat(R.id.btn_approval, "setAlpha", if (approval > 0) 1.0f else 0.4f)
        remoteViews.setOnClickPendingIntent(
            R.id.btn_approval,
            buildActionPendingIntent(context, ACTION_APPROVAL, 101)
        )

        // Completed button
        remoteViews.setTextViewText(R.id.btn_completed, "$completed done")
        remoteViews.setFloat(R.id.btn_completed, "setAlpha", if (completed > 0) 1.0f else 0.4f)
        remoteViews.setOnClickPendingIntent(
            R.id.btn_completed,
            buildActionPendingIntent(context, ACTION_COMPLETED, 102)
        )

        val contentIntent = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
        )

        return NotificationCompat.Builder(context, CHANNEL_ONGOING)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setStyle(NotificationCompat.DecoratedCustomViewStyle())
            .setCustomContentView(remoteViews)
            .setCustomBigContentView(remoteViews)
            .setOngoing(true)
            .setContentIntent(contentIntent)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .build()
    }

    private fun buildTitle(working: Int, approval: Int, completed: Int): String {
        val parts = mutableListOf<String>()
        if (working > 0) parts.add("$working working")
        if (approval > 0) parts.add("$approval pending")
        if (completed > 0) parts.add("$completed completed")
        return if (parts.isNotEmpty()) "cc-monitor: ${parts.joinToString(" | ")}" else "cc-monitor"
    }

    private fun buildActionPendingIntent(
        context: Context,
        action: String,
        requestCode: Int
    ): PendingIntent {
        val intent = Intent(context, NotificationForegroundService::class.java).apply {
            this.action = action
        }
        return PendingIntent.getService(
            context,
            requestCode,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
        )
    }

    fun showAlert(context: Context, sessionName: String, state: String) {
        val (title, body) = when (state) {
            "pending_approval" -> "⚠ Approval Needed" to "Claude needs permission to proceed"
            "pending_review" -> "✅ Response Ready" to "Claude finished — review the output"
            "all_done" -> "🏁 Session Ended" to "Claude Code session completed"
            else -> "State Change" to "Session is now $state"
        }

        // Sound and vibration are controlled at the channel level.
        // When the user toggles settings, the channel is recreated
        // with the appropriate sound/vibration configuration.

        val alertId = (System.currentTimeMillis() % 100000).toInt()

        val contentIntent = PendingIntent.getActivity(
            context,
            alertId,
            Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
        )

        NotificationManagerCompat.from(context).notify(
            alertId,
            NotificationCompat.Builder(context, CHANNEL_ALERT)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle(title)
                .setContentText("$sessionName · $body")
                .setContentIntent(contentIntent)
                .setAutoCancel(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                .build()
        )
    }
}
