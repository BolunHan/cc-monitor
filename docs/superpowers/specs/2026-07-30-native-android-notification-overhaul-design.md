# Native Android Notification Overhaul

**Date:** 2026-07-30
**Status:** Approved
**Scope:** Replace Flutter `flutter_local_notifications` with native Android `ForegroundService` + custom `RemoteViews` notification

## Motivation

`flutter_local_notifications` cannot deliver the required notification UX:
1. Sound/vibration unreliable across Android versions
2. No colored action button backgrounds (only text color via `titleColor`)
3. Notification dies when app is backgrounded
4. Lock screen visibility not configurable through the package
5. Ongoing notification desyncs from actual session state

## Architecture

```
Flutter (Dart)                              Native Android (Kotlin)
─────────────                              ──────────────────────
SSE stream ──┐
manual refresh ──→ SessionProvider              NotificationForegroundService
lifecycle ──┘         │                              │
                       │  MethodChannel               │
                       ├──────────────────────────────┤
                       │  updateSticky(counts,label)  │──→ ongoing notification (RemoteViews)
                       │  showAlert(name,state)       │──→ alert notification (sound+vibrate)
                       │  updateSettings(sound,vib)   │──→ channel config
                       │  startService / stopService  │──→ lifecycle
                       │                              │
                       │  onActionTap(action)         │──→ open app / filter
                       ├──────────────────────────────┤
```

## Notification Channels

| Channel | ID | Importance | Sound | Vibration | Lock Screen | Ongoing |
|---------|----|-----------|-------|-----------|-------------|---------|
| Ongoing | `cc_monitor_ongoing` | `IMPORTANCE_HIGH` | silent | none | `VISIBILITY_PUBLIC` | yes |
| Alert | `cc_monitor_alerts` | `IMPORTANCE_HIGH` | default | `[0,200,100,200]` | `VISIBILITY_PUBLIC` | no |

## Custom Ongoing Notification Layout

```
┌───────────────────────────────────────────────────┐
│ 🔔  cc-monitor                                    │
│     Connected to: 192.168.3.25:9876                │
│                                                    │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────┐ │
│  │  3 working   │ │  1 pending   │ │  0 done     │ │
│  │   #58A6FF    │ │   #D97706    │ │  #22C55E    │ │
│  └──────────────┘ └──────────────┘ └────────────┘ │
└───────────────────────────────────────────────────┘
```

- Three `TextView` buttons with colored shape drawable backgrounds + rounded corners (8dp)
- Each fires a `PendingIntent` broadcast to the foreground service
- Zero-count buttons shown dimmed (alpha 0.4)
- Service forwards tap to Flutter via MethodChannel callback → opens DashboardScreen

## MethodChannel Contract

Channel name: `cc_monitor/notifications`

### Flutter → Native

| Method | Args | When |
|--------|------|------|
| `startService` | — | App launch |
| `stopService` | — | All servers removed / disconnect |
| `updateSticky` | `{working, approval, review, serverLabel}` | Every state mutation |
| `showAlert` | `{sessionName, state}` | State transition to approval/review/all_done |
| `updateSettings` | `{sound, vibrate}` | Settings toggle change |

### Native → Flutter

| Callback | Data | Action |
|----------|------|--------|
| `onActionTap` | `"working"` / `"approval"` / `"completed"` | Bring app to foreground |

## State Update Triggers

Every call to `notifyListeners()` in SessionProvider is accompanied by `_syncToNativeNotification()`:

- SSE `state_update` → `_upsert()` → sync
- Manual pull-to-refresh → `loadSessions()` → sync
- SSE connect → `connectSse()` → sync
- SSE disconnect/clear → `_clear()` → sync
- Server change → `loadSessions()` after reconfigure → sync
- App resume from background → `AppLifecycleListener` → `loadSessions()` → sync
- Settings toggle → `updateSettings()` → native channel

## Files

### New Files (Native Android)

| File | Purpose |
|------|---------|
| `android/app/src/main/kotlin/com/ccmonitor/app/NotificationForegroundService.kt` | Foreground service managing ongoing notification, handles action taps |
| `android/app/src/main/kotlin/com/ccmonitor/app/NotificationHelper.kt` | Channel creation, alert notification builder, RemoteViews builder |
| `android/app/src/main/res/layout/notification_ongoing.xml` | Custom RemoteViews layout with 3 colored buttons |
| `android/app/src/main/res/drawable/btn_notify_blue.xml` | Blue button shape drawable (#58A6FF, rounded 8dp) |
| `android/app/src/main/res/drawable/btn_notify_yellow.xml` | Yellow button shape drawable (#D97706, rounded 8dp) |
| `android/app/src/main/res/drawable/btn_notify_green.xml` | Green button shape drawable (#22C55E, rounded 8dp) |

### Modified Files (Native Android)

| File | Change |
|------|--------|
| `android/app/src/main/kotlin/com/ccmonitor/app/MainActivity.kt` | Add MethodChannel handler, start/stop service |
| `android/app/src/main/AndroidManifest.xml` | Declare service (`foregroundServiceType="dataSync"`), add `FOREGROUND_SERVICE_DATA_SYNC`, `RECEIVE_BOOT_COMPLETED`, `SCHEDULE_EXACT_ALARM` permissions |

### New/Replaced Files (Flutter)

| File | Purpose |
|------|---------|
| `lib/services/notification_service.dart` | Rewrite as thin MethodChannel wrapper (same public API, different internals) |

### Modified Files (Flutter)

| File | Change |
|------|--------|
| `lib/main.dart` | Start service after `NotificationService.init()`, add `AppLifecycleListener` |
| `lib/providers/session_provider.dart` | Call `_syncToNativeNotification()` after every state mutation |
| `lib/screens/dashboard_screen.dart` | Replace `flutter_local_notifications` permission request with native |
| `lib/screens/settings_screen.dart` | Route `updateSettings` to native channel |
| `pubspec.yaml` | Remove `flutter_local_notifications` dependency |

## Build

No changes to `Dockerfile.flutter`. Kotlin source compiles as part of the standard Flutter Android Gradle build. Build proxy: `192.168.3.25:7780`.

```bash
docker build --build-arg HTTP_PROXY=http://192.168.3.25:7780 --build-arg HTTPS_PROXY=http://192.168.3.25:7780 \
  -f Dockerfile.flutter -t cc-monitor-flutter .
docker run --rm -it \
  -e HTTP_PROXY=http://192.168.3.25:7780 -e HTTPS_PROXY=http://192.168.3.25:7780 \
  -v ${PWD}:/build --workdir /build/android_app \
  cc-monitor-flutter flutter build apk --release
```

## Testing

- Manual: Install APK on Android device, verify ongoing notification appears with colored buttons
- Manual: Trigger state transitions, verify alert notifications fire with sound+vibration
- Manual: Lock screen, verify ongoing notification visible
- Manual: Swipe app away, verify foreground service notification persists
- Manual: Toggle sound/vibration in settings, verify next alert respects setting
