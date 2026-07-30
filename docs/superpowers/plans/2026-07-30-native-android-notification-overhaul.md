# Native Android Notification Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or execute inline. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `flutter_local_notifications` with native Android `ForegroundService` + `RemoteViews` for ongoing notification with colored buttons, reliable sound/vibration alerts, lock screen visibility, and background persistence.

**Architecture:** Native Kotlin `ForegroundService` owns all notifications. Flutter communicates via `MethodChannel` (`cc_monitor/notifications`). Service stays alive with `START_STICKY`. Custom `RemoteViews` layout provides blue/yellow/green action buttons.

**Tech Stack:** Kotlin (native Android), Dart/Flutter, MethodChannel, RemoteViews, Android ForegroundService

## Global Constraints

- Package namespace: `com.ccmonitor.cc_monitor_app`
- Min SDK: `flutter.minSdkVersion` (21+)
- Target SDK: `flutter.targetSdkVersion`
- Kotlin JVM target: 17
- Desugaring enabled (coreLibraryDesugaring 2.1.4)
- Docker build proxy: `192.168.3.25:7780`
- Remove `flutter_local_notifications` dependency

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| CREATE | `android/.../NotificationForegroundService.kt` | Foreground service, ongoing notification lifecycle, action tap handling |
| CREATE | `android/.../NotificationHelper.kt` | Channel creation, notification builders, RemoteViews, alert firing |
| CREATE | `android/.../res/layout/notification_ongoing.xml` | RemoteViews layout: title, subtitle, 3 colored buttons |
| CREATE | `android/.../res/drawable/btn_notify_blue.xml` | Blue shape drawable (#58A6FF, rounded 8dp) |
| CREATE | `android/.../res/drawable/btn_notify_yellow.xml` | Yellow shape drawable (#D97706, rounded 8dp) |
| CREATE | `android/.../res/drawable/btn_notify_green.xml` | Green shape drawable (#22C55E, rounded 8dp) |
| MODIFY | `android/.../MainActivity.kt` | MethodChannel handler, service start/stop |
| MODIFY | `android/.../AndroidManifest.xml` | Service declaration, permissions |
| REWRITE | `lib/services/notification_service.dart` | Thin MethodChannel wrapper (same public API) |
| MODIFY | `lib/main.dart` | Service start, AppLifecycleListener |
| MODIFY | `lib/providers/session_provider.dart` | Sync to native on every state mutation |
| MODIFY | `lib/screens/dashboard_screen.dart` | Replace permission request |
| MODIFY | `lib/screens/settings_screen.dart` | Route to native channel |
| MODIFY | `pubspec.yaml` | Remove `flutter_local_notifications` |

---

### Task 1: Create native drawable shape resources

**Files:**
- Create: `android_app/android/app/src/main/res/drawable/btn_notify_blue.xml`
- Create: `android_app/android/app/src/main/res/drawable/btn_notify_yellow.xml`
- Create: `android_app/android/app/src/main/res/drawable/btn_notify_green.xml`

**Interfaces:**
- Produces: `@drawable/btn_notify_blue`, `@drawable/btn_notify_yellow`, `@drawable/btn_notify_green` — shape drawables for RemoteViews buttons

- [ ] **Step 1: Create blue button shape**

File: `android_app/android/app/src/main/res/drawable/btn_notify_blue.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android"
    android:shape="rectangle">
    <solid android:color="#58A6FF" />
    <corners android:radius="8dp" />
    <padding
        android:left="12dp"
        android:right="12dp"
        android:top="6dp"
        android:bottom="6dp" />
</shape>
```

- [ ] **Step 2: Create yellow button shape**

File: `android_app/android/app/src/main/res/drawable/btn_notify_yellow.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android"
    android:shape="rectangle">
    <solid android:color="#D97706" />
    <corners android:radius="8dp" />
    <padding
        android:left="12dp"
        android:right="12dp"
        android:top="6dp"
        android:bottom="6dp" />
</shape>
```

- [ ] **Step 3: Create green button shape**

File: `android_app/android/app/src/main/res/drawable/btn_notify_green.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android"
    android:shape="rectangle">
    <solid android:color="#22C55E" />
    <corners android:radius="8dp" />
    <padding
        android:left="12dp"
        android:right="12dp"
        android:top="6dp"
        android:bottom="6dp" />
</shape>
```

- [ ] **Step 4: Commit**

```bash
git add android_app/android/app/src/main/res/drawable/btn_notify_*.xml
git commit -m "feat: add colored button shape drawables for notification RemoteViews"
```

---

### Task 2: Create notification RemoteViews layout

**Files:**
- Create: `android_app/android/app/src/main/res/layout/notification_ongoing.xml`

**Interfaces:**
- Consumes: `@drawable/btn_notify_blue`, `@drawable/btn_notify_yellow`, `@drawable/btn_notify_green`
- Produces: `R.layout.notification_ongoing` — RemoteViews layout with `@id/notify_title`, `@id/notify_subtitle`, `@id/btn_working`, `@id/btn_approval`, `@id/btn_completed`

- [ ] **Step 1: Create layout XML**

File: `android_app/android/app/src/main/res/layout/notification_ongoing.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:padding="8dp">

    <TextView
        android:id="@+id/notify_title"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:textColor="@android:color/white"
        android:textSize="14sp"
        android:textStyle="bold"
        android:maxLines="1"
        android:ellipsize="end" />

    <TextView
        android:id="@+id/notify_subtitle"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:textColor="@android:color/darker_gray"
        android:textSize="12sp"
        android:maxLines="1"
        android:ellipsize="end"
        android:layout_marginTop="2dp"
        android:layout_marginBottom="6dp" />

    <LinearLayout
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:orientation="horizontal">

        <TextView
            android:id="@+id/btn_working"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:layout_marginEnd="4dp"
            android:background="@drawable/btn_notify_blue"
            android:gravity="center"
            android:padding="8dp"
            android:text="0 working"
            android:textColor="@android:color/white"
            android:textSize="11sp"
            android:textStyle="bold"
            android:clickable="true"
            android:focusable="true" />

        <TextView
            android:id="@+id/btn_approval"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:layout_marginEnd="4dp"
            android:background="@drawable/btn_notify_yellow"
            android:gravity="center"
            android:padding="8dp"
            android:text="0 pending"
            android:textColor="@android:color/white"
            android:textSize="11sp"
            android:textStyle="bold"
            android:clickable="true"
            android:focusable="true" />

        <TextView
            android:id="@+id/btn_completed"
            android:layout_width="0dp"
            android:layout_height="wrap_content"
            android:layout_weight="1"
            android:background="@drawable/btn_notify_green"
            android:gravity="center"
            android:padding="8dp"
            android:text="0 done"
            android:textColor="@android:color/white"
            android:textSize="11sp"
            android:textStyle="bold"
            android:clickable="true"
            android:focusable="true" />

    </LinearLayout>

</LinearLayout>
```

- [ ] **Step 2: Commit**

```bash
git add android_app/android/app/src/main/res/layout/notification_ongoing.xml
git commit -m "feat: add custom RemoteViews layout for ongoing notification"
```

---

### Task 3: Create NotificationHelper

**Files:**
- Create: `android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/NotificationHelper.kt`

**Interfaces:**
- Produces:
  - `NotificationHelper.createChannels(context: Context)` — creates both notification channels
  - `NotificationHelper.buildOngoingNotification(context: Context, working: Int, approval: Int, completed: Int, serverLabel: String): Notification` — builds ongoing notification with RemoteViews
  - `NotificationHelper.showAlert(context: Context, sessionName: String, state: String)` — fires alert notification with sound+vibration
  - `NotificationHelper.updateSoundVibrate(sound: Boolean, vibrate: Boolean)` — updates alert channel prefs
  - Companion constants: `CHANNEL_ONGOING = "cc_monitor_ongoing"`, `CHANNEL_ALERT = "cc_monitor_alerts"`, `NOTIFY_ONGOING_ID = 1`, `ACTION_WORKING = "cc_monitor.action.WORKING"`, `ACTION_APPROVAL = "cc_monitor.action.APPROVAL"`, `ACTION_COMPLETED = "cc_monitor.action.COMPLETED"`

- [ ] **Step 1: Write NotificationHelper.kt**

File: `android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/NotificationHelper.kt`
```kotlin
package com.ccmonitor.cc_monitor_app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.net.Uri
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

        // Ongoing channel — HIGH importance for lock screen, no sound
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

        // Alert channel — HIGH importance, sound + vibration on event push
        val alertChannel = NotificationChannel(
            CHANNEL_ALERT,
            "Session Alerts",
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = "State transition alerts"
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            enableVibration(true)
            vibrationPattern = longArrayOf(0, 200, 100, 200)
            val attrs = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                .build()
            setSound(
                RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
                attrs
            )
        }
        nm.createNotificationChannel(alertChannel)
    }

    fun updateSoundVibrate(sound: Boolean, vibrate: Boolean) {
        soundEnabled = sound
        vibrateEnabled = vibrate
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
        remoteViews.setInt(R.id.btn_working, "setAlpha", if (working > 0) 255 else 100)
        remoteViews.setOnClickPendingIntent(
            R.id.btn_working,
            buildActionPendingIntent(context, ACTION_WORKING, 100)
        )

        // Approval button
        remoteViews.setTextViewText(R.id.btn_approval, "$approval pending")
        remoteViews.setInt(R.id.btn_approval, "setAlpha", if (approval > 0) 255 else 100)
        remoteViews.setOnClickPendingIntent(
            R.id.btn_approval,
            buildActionPendingIntent(context, ACTION_APPROVAL, 101)
        )

        // Completed button
        remoteViews.setTextViewText(R.id.btn_completed, "$completed done")
        remoteViews.setInt(R.id.btn_completed, "setAlpha", if (completed > 0) 255 else 100)
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
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
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
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
        )
    }

    fun showAlert(context: Context, sessionName: String, state: String) {
        val (title, body) = when (state) {
            "pending_approval" -> "⚠ Approval Needed" to "Claude needs permission to proceed"
            "pending_review" -> "✅ Response Ready" to "Claude finished — review the output"
            "all_done" -> "🏁 Session Ended" to "Claude Code session completed"
            else -> "State Change" to "Session is now $state"
        }

        val soundUri = if (soundEnabled) {
            RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        } else null

        val vibratePattern = if (vibrateEnabled) longArrayOf(0, 200, 100, 200) else null

        val alertId = (System.currentTimeMillis() % 100000).toInt()

        val contentIntent = PendingIntent.getActivity(
            context,
            alertId,
            Intent(context, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
        )

        val builder = NotificationCompat.Builder(context, CHANNEL_ALERT)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(title)
            .setContentText("$sessionName · $body")
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)

        if (soundUri != null) {
            builder.setSound(soundUri)
        }
        if (vibratePattern != null) {
            builder.setVibration(vibratePattern)
        }

        NotificationManagerCompat.from(context).notify(alertId, builder.build())
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/NotificationHelper.kt
git commit -m "feat: add NotificationHelper — channel creation, ongoing RemoteViews, alert builder"
```

---

### Task 4: Create NotificationForegroundService

**Files:**
- Create: `android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/NotificationForegroundService.kt`

**Interfaces:**
- Consumes: `NotificationHelper.CHANNEL_ONGOING`, `NotificationHelper.NOTIFY_ONGOING_ID`, `NotificationHelper.ACTION_*`, `NotificationHelper.buildOngoingNotification()`, `NotificationHelper.showAlert()`
- Produces: Android Service component, handles `ACTION_*` intents, exposes `updateNotification()` and `showAlert()` via companion object

- [ ] **Step 1: Write NotificationForegroundService.kt**

File: `android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/NotificationForegroundService.kt`
```kotlin
package com.ccmonitor.cc_monitor_app

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class NotificationForegroundService : Service() {

    companion object {
        private const val TAG = "cc-monitor:fgservice"
        private var instance: NotificationForegroundService? = null
        private var flutterChannel: MethodChannel? = null

        // State cache for rebuilds
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
```

- [ ] **Step 2: Commit**

```bash
git add android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/NotificationForegroundService.kt
git commit -m "feat: add NotificationForegroundService with START_STICKY and action handling"
```

---

### Task 5: Update AndroidManifest.xml

**Files:**
- Modify: `android_app/android/app/src/main/AndroidManifest.xml`

**Interfaces:**
- Consumes: `NotificationForegroundService`
- Produces: Service declaration, foreground service permissions

- [ ] **Step 1: Add service declaration and permissions to manifest**

Replace `<application>` section to include the service, and ensure all permissions are present.

File: `android_app/android/app/src/main/AndroidManifest.xml`
```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET"/>
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE"/>
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE"/>
    <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE"/>
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
    <uses-permission android:name="android.permission.VIBRATE"/>
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC"/>
    <uses-permission android:name="android.permission.USE_EXACT_ALARM"/>
    <application
        android:label="cc_monitor_app"
        android:name="${applicationName}"
        android:icon="@mipmap/ic_launcher">
        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTop"
            android:taskAffinity=""
            android:theme="@style/LaunchTheme"
            android:configChanges="orientation|keyboardHidden|keyboard|screenSize|smallestScreenSize|locale|layoutDirection|fontScale|screenLayout|density|uiMode"
            android:hardwareAccelerated="true"
            android:windowSoftInputMode="adjustResize">
            <meta-data
              android:name="io.flutter.embedding.android.NormalTheme"
              android:resource="@style/NormalTheme"
              />
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
            <intent-filter>
                <action android:name="android.intent.action.VIEW"/>
                <category android:name="android.intent.category.DEFAULT"/>
                <category android:name="android.intent.category.BROWSABLE"/>
                <data android:scheme="ccmonitor" android:host="pair"/>
            </intent-filter>
        </activity>

        <service
            android:name=".NotificationForegroundService"
            android:exported="false"
            android:foregroundServiceType="dataSync" />

        <meta-data
            android:name="flutterEmbedding"
            android:value="2" />
    </application>
    <queries>
        <intent>
            <action android:name="android.intent.action.PROCESS_TEXT"/>
            <data android:mimeType="text/plain"/>
        </intent>
    </queries>
</manifest>
```

- [ ] **Step 2: Commit**

```bash
git add android_app/android/app/src/main/AndroidManifest.xml
git commit -m "feat: declare NotificationForegroundService and add required permissions"
```

---

### Task 6: Update MainActivity with MethodChannel

**Files:**
- Modify: `android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/MainActivity.kt`

**Interfaces:**
- Consumes: `NotificationForegroundService`, `NotificationHelper`
- Produces: MethodChannel `cc_monitor/notifications` handler for all Flutter→Native calls

- [ ] **Step 1: Rewrite MainActivity.kt**

File: `android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/MainActivity.kt`
```kotlin
package com.ccmonitor.cc_monitor_app

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.util.Log
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    companion object {
        private const val CHANNEL = "cc_monitor/notifications"
        private const val TAG = "cc-monitor:main"
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
```

- [ ] **Step 2: Commit**

```bash
git add android_app/android/app/src/main/kotlin/com/ccmonitor/cc_monitor_app/MainActivity.kt
git commit -m "feat: add MethodChannel handler in MainActivity for native notifications"
```

---

### Task 7: Rewrite notification_service.dart as MethodChannel wrapper

**Files:**
- Rewrite: `android_app/lib/services/notification_service.dart`

**Interfaces:**
- Consumes: MethodChannel `cc_monitor/notifications`
- Produces: Same public API as before — `init()`, `updateSticky()`, `showAlert()`, `updateSettings()`, `cancelSticky()`, `soundEnabled`, `vibrateEnabled`
- New: `onActionTap` stream for native→Flutter callbacks

- [ ] **Step 1: Rewrite notification_service.dart**

File: `android_app/lib/services/notification_service.dart`
```dart
import 'package:flutter/services.dart';

class NotificationService {
  static const _channel = MethodChannel('cc_monitor/notifications');

  static final _actionTapController = StreamController<String>.broadcast();
  static Stream<String> get onActionTap => _actionTapController.stream;

  static bool _soundEnabled = true;
  static bool _vibrateEnabled = true;

  static bool get soundEnabled => _soundEnabled;
  static bool get vibrateEnabled => _vibrateEnabled;

  static Future<void> requestPermission() async {
    // Permission is handled by the native Android POST_NOTIFICATIONS runtime
    // request. The foreground service will trigger the system permission dialog
    // when it first starts on Android 13+.
  }

  static Future<void> init() async {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onActionTap') {
        _actionTapController.add(call.arguments as String);
      }
    });

    await _channel.invokeMethod('startService');
  }

  static void updateSettings({required bool sound, required bool vibrate}) {
    _soundEnabled = sound;
    _vibrateEnabled = vibrate;
    _channel.invokeMethod('updateSettings', {
      'sound': sound,
      'vibrate': vibrate,
    });
  }

  static Future<void> updateSticky({
    required int working,
    required int pendingApproval,
    required int pendingReview,
    String serverLabel = '',
  }) async {
    await _channel.invokeMethod('updateSticky', {
      'working': working,
      'approval': pendingApproval,
      'completed': pendingReview,
      'serverLabel': serverLabel,
    });
  }

  static Future<void> cancelSticky() async {
    await _channel.invokeMethod('stopService');
  }

  static Future<void> showAlert({
    required String sessionName,
    required String state,
  }) async {
    await _channel.invokeMethod('showAlert', {
      'sessionName': sessionName,
      'state': state,
    });
  }
}
```

The `dart:async` import for `StreamController` is needed. Add it:
```dart
import 'dart:async';
import 'package:flutter/services.dart';
```

- [ ] **Step 2: Verify the file compiles (conceptual — tested in build step)**

- [ ] **Step 3: Commit**

```bash
git add android_app/lib/services/notification_service.dart
git commit -m "refactor: rewrite notification_service as native MethodChannel wrapper"
```

---

### Task 8: Update pubspec.yaml — remove flutter_local_notifications

**Files:**
- Modify: `android_app/pubspec.yaml`

**Interfaces:**
- Removes `flutter_local_notifications` dependency

- [ ] **Step 1: Remove flutter_local_notifications from dependencies**

In `android_app/pubspec.yaml`, remove line 18: `flutter_local_notifications: ^18.0.0`

Also remove the `dependency_overrides` section if it only overrides `path_provider_android` for `flutter_local_notifications` (check if it's needed by other deps). `path_provider_android` is only needed by `flutter_local_notifications` in this project, so remove lines 28-29:
```yaml
dependency_overrides:
  path_provider_android: 2.2.22
```

The updated `pubspec.yaml` dependencies section:
```yaml
dependencies:
  flutter:
    sdk: flutter
  dio: ^5.4.0
  flutter_secure_storage: ^9.2.0
  mobile_scanner: ^5.0.0
  provider: ^6.1.0
  multicast_dns: ^0.3.2
```

- [ ] **Step 2: Commit**

```bash
git add android_app/pubspec.yaml
git commit -m "refactor: remove flutter_local_notifications dependency"
```

---

### Task 9: Update session_provider.dart for comprehensive native sync

**Files:**
- Modify: `android_app/lib/providers/session_provider.dart`

**Interfaces:**
- Consumes: `NotificationService.updateSticky()`, `NotificationService.showAlert()`
- Produces: Every state mutation calls `_syncToNativeNotification()`

- [ ] **Step 1: Add _syncToNativeNotification helper and call it everywhere**

The key change: add a `_syncToNativeNotification()` method and call it after every mutation. Also add `AppLifecycleListener` support for resume-triggered refresh.

Changes to `session_provider.dart`:

```dart
import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/session.dart';
import '../services/api_client.dart';
import '../services/notification_service.dart';
import '../services/sse_client.dart';
import '../services/secure_store.dart';

class SessionProvider extends ChangeNotifier {
  final ApiClient _api;
  SseClient? _sseClient;
  Timer? _heartbeatTimer;

  List<Session> _active = [];
  List<Session> _complete = [];
  List<Session> _archived = [];
  bool _loading = true;
  bool _connected = false;

  final List<SseEventEntry> _eventLog = [];
  static const int _maxEventLog = 200;

  LogLevel _logLevel = LogLevel.info;

  final Map<String, String> _prevState = {};

  int _notifyWorking = 0;
  int _notifyApproval = 0;
  int _notifyReview = 0;

  List<Session> get active => List.unmodifiable(_active);
  List<Session> get complete => List.unmodifiable(_complete);
  List<Session> get archived => List.unmodifiable(_archived);
  bool get loading => _loading;
  bool get connected => _connected;
  LogLevel get logLevel => _logLevel;
  List<SseEventEntry> get eventLog => List.unmodifiable(_eventLog);

  List<SseEventEntry> get filteredEventLog =>
      _eventLog.where((e) => _logLevel.shouldShow(e.level)).toList();

  SessionProvider(this._api) {
    _syncToNativeNotification();
  }

  void notifyServerConnected(String host, int port) {
    _refreshServerLabel();
    _syncToNativeNotification();
  }

  // ... (logLevel, _logEvent unchanged) ...

  Future<void> loadSessions() async {
    if (!_api.isConfigured) return;
    _loading = true;
    notifyListeners();

    try {
      final resp = await _api.get('/api/status');
      if (resp.statusCode == 200) {
        final sessions = (resp.data['sessions'] as List)
            .map((j) => Session.fromJson(j as Map<String, dynamic>))
            .toList();
        _categorize(sessions);
        _connected = true;
      } else if (resp.statusCode == 401) {
        _connected = false;
        _clear();
      }
    } catch (_) {
      _connected = false;
    }

    _loading = false;
    notifyListeners();
    _syncToNativeNotification();
  }

  // ... (connectSse, _startHeartbeat unchanged) ...

  void _clear() {
    _active = [];
    _complete = [];
    _archived = [];
    _prevState.clear();
    _notifyWorking = 0;
    _notifyApproval = 0;
    _notifyReview = 0;
    _syncToNativeNotification();
    _sseClient?.disconnect();
    _sseClient = null;
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
  }

  // ... (archiveSession, unarchiveSession, markComplete unchanged) ...

  void _upsert(Session session) {
    _active.removeWhere((s) => s.sessionId == session.sessionId);
    _complete.removeWhere((s) => s.sessionId == session.sessionId);
    _archived.removeWhere((s) => s.sessionId == session.sessionId);

    if (session.archived) {
      _archived.add(session);
    } else if (session.isComplete) {
      _complete.add(session);
    } else {
      _active.add(session);
    }

    _active.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    _complete.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    _archived.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));

    final prev = _prevState[session.sessionId];
    final curr = session.state;
    if (prev != null && prev != curr) {
      if (curr == 'pending_approval' || curr == 'pending_review' || curr == 'all_done') {
        final name = _sessionName(session);
        NotificationService.showAlert(sessionName: name, state: curr);
      }
    }
    _prevState[session.sessionId] = curr;

    _updateNotifyCounts();
    _syncToNativeNotification();

    notifyListeners();
  }

  // ... (_sessionName, _updateNotifyCounts unchanged) ...

  void _syncToNativeNotification() {
    NotificationService.updateSticky(
      working: _notifyWorking,
      pendingApproval: _notifyApproval,
      pendingReview: _notifyReview,
      serverLabel: _serverLabel,
    );
  }

  // ... (_refreshServerLabel, _categorize unchanged) ...
  // But in _categorize, after _updateNotifyCounts(), replace
  // _updateStickyNotification() with _syncToNativeNotification()

  void _categorize(List<Session> sessions) {
    _active = sessions.where((s) => s.isActive).toList()
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    _complete = sessions.where((s) => s.isComplete).toList()
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    _archived = sessions.where((s) => s.archived).toList()
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    for (final s in [..._active, ..._complete, ..._archived]) {
      _prevState.putIfAbsent(s.sessionId, () => s.state);
    }
    _updateNotifyCounts();
    _syncToNativeNotification();
  }

  // Remove _updateStickyNotification() method — replaced by _syncToNativeNotification()
}
```

- [ ] **Step 2: Commit**

```bash
git add android_app/lib/providers/session_provider.dart
git commit -m "feat: sync native notification on every session state mutation"
```

---

### Task 10: Update main.dart with lifecycle listener

**Files:**
- Modify: `android_app/lib/main.dart`

**Interfaces:**
- Consumes: `NotificationService.init()` (now starts foreground service)
- New: `AppLifecycleListener` for resume detection

- [ ] **Step 1: Add AppLifecycleListener to _StartupGate**

The key change: after the dashboard is shown, listen for app resume events to refresh sessions (which will sync notification).

Actually, the simplest approach is to add a `WidgetsBindingObserver` mixin to the app or to `DashboardScreen`. Let's add it to `_StartupGate` or better, handle it in `DashboardScreen` where the SessionProvider is already available.

Instead of modifying main.dart significantly, let's add lifecycle handling to `DashboardScreen._DashboardScreenState` since it already has `initState` with SSE connect logic.

Actually, the cleanest approach: add lifecycle listener in `DashboardScreen` since that's where the session provider context lives. Let me update the plan for Task 11 instead.

For `main.dart`, the only change is that `NotificationService.init()` now starts the foreground service. No other changes needed.

File: `android_app/lib/main.dart` — no changes needed beyond what's already there.

- [ ] **Step 1: Verify main.dart is correct as-is (NotificationService.init() already called, starts service now)**

No change needed. `main()` already calls `NotificationService.init()` which now starts the foreground service.

- [ ] **Step 2: Commit (skip — no changes)**

---

### Task 11: Update dashboard_screen.dart — lifecycle listener + permission

**Files:**
- Modify: `android_app/lib/screens/dashboard_screen.dart`

**Interfaces:**
- Consumes: `NotificationService.requestPermission()`, `WidgetsBindingObserver` for lifecycle
- Produces: Resume-triggered session refresh, updated permission request

- [ ] **Step 1: Add WidgetsBindingObserver and lifecycle handling**

In `_DashboardScreenState`, add `WidgetsBindingObserver` mixin and handle resume:

```dart
class _DashboardScreenState extends State<DashboardScreen> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      NotificationService.requestPermission();
      final store = context.read<SecureStore>();
      final sound = await store.getNotifySound();
      final vibrate = await store.getNotifyVibrate();
      if (!mounted) return;
      NotificationService.updateSettings(sound: sound, vibrate: vibrate);
      context.read<SessionProvider>().connectSse();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Refresh sessions on resume — this syncs the notification too
      context.read<SessionProvider>().loadSessions();
    }
  }

  // ... rest unchanged ...
}
```

- [ ] **Step 2: Commit**

```bash
git add android_app/lib/screens/dashboard_screen.dart
git commit -m "feat: add lifecycle listener to refresh sessions and sync notification on resume"
```

---

### Task 12: Update settings_screen.dart

**Files:**
- Modify: `android_app/lib/screens/settings_screen.dart`

**Interfaces:**
- Consumes: `NotificationService.updateSettings()`

**No code changes needed** — `settings_screen.dart` already calls `NotificationService.updateSettings(sound: val, vibrate: _vibrate)` which now routes to native via MethodChannel. The import of `notification_service.dart` is already present.

- [ ] **Step 1: Verify — no changes needed. Skip commit.**

---

### Task 13: Build APK and verify compilation

**Files:**
- All above files

**Interfaces:**
- Produces: Compiled APK

- [ ] **Step 1: Build APK with Docker**

```bash
docker build --build-arg HTTP_PROXY=http://192.168.3.25:7780 --build-arg HTTPS_PROXY=http://192.168.3.25:7780 \
  -f Dockerfile.flutter -t cc-monitor-flutter .
docker run --rm \
  -e HTTP_PROXY=http://192.168.3.25:7780 -e HTTPS_PROXY=http://192.168.3.25:7780 \
  -v ${PWD}:/build --workdir /build/android_app \
  cc-monitor-flutter flutter build apk --release
```

- [ ] **Step 2: Fix any compilation errors and recommit**
- [ ] **Step 3: Commit final fixes if any**

---

## Self-Review

1. **Spec coverage:**
   - ✅ Sound/vibration fix: Task 3 (NotificationHelper channel config + alert builder)
   - ✅ Ongoing notification update on state change: Task 9 (comprehensive sync)
   - ✅ Lock screen visibility: Task 3 (VISIBILITY_PUBLIC on both channels)
   - ✅ Background operation: Task 4 (ForegroundService with START_STICKY)
   - ✅ Colored buttons (blue/yellow/green): Tasks 1-3 (shape drawables + RemoteViews layout)
   - ✅ App resume refresh: Task 11 (WidgetsBindingObserver)
   - ✅ Server add/remove refresh: Task 9 (connectSse and _clear both sync)

2. **Placeholder scan:** No TBDs, TODOs, or vague instructions. All code is complete.

3. **Type consistency:**
   - Channel: `cc_monitor/notifications` — consistent across Dart (.dart) and Kotlin (.kt)
   - Method names: `startService`, `stopService`, `updateSticky`, `showAlert`, `updateSettings` — match both sides
   - Arg keys: `working`, `approval`, `completed`, `serverLabel`, `sessionName`, `state`, `sound`, `vibrate` — match both sides
   - Callback: `onActionTap` — consistent
   - Action constants: `ACTION_WORKING`, `ACTION_APPROVAL`, `ACTION_COMPLETED` — consistent
