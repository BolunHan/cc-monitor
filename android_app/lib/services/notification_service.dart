import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  static const _channelStickyId = 'cc_monitor_sticky';
  static const _channelStickyName = 'Session Monitor';
  static const _channelAlertId = 'cc_monitor_alerts';
  static const _channelAlertName = 'Session Alerts';
  static const _stickyNotificationId = 1;

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static bool _initialized = false;
  static bool _soundEnabled = true;
  static bool _vibrateEnabled = true;
  static String _serverLabel = '';

  static bool get soundEnabled => _soundEnabled;
  static bool get vibrateEnabled => _vibrateEnabled;

  static Future<void> requestPermission() async {
    if (Platform.isAndroid) {
      final android = _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();
      await android?.requestNotificationsPermission();
    }
  }

  static Future<void> init() async {
    if (_initialized) return;

    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosInit = DarwinInitializationSettings();
    const initSettings = InitializationSettings(
      android: androidInit,
      iOS: iosInit,
    );

    await _plugin.initialize(
      initSettings,
      onDidReceiveNotificationResponse: _onTap,
    );

    final androidPlugin = _plugin.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();

    if (androidPlugin != null) {
      await androidPlugin.createNotificationChannel(
        const AndroidNotificationChannel(
          _channelStickyId,
          _channelStickyName,
          importance: Importance.low,
          playSound: false,
          enableVibration: false,
          showBadge: false,
        ),
      );

      await androidPlugin.createNotificationChannel(
        AndroidNotificationChannel(
          _channelAlertId,
          _channelAlertName,
          importance: Importance.high,
          playSound: _soundEnabled,
          enableVibration: _vibrateEnabled,
        ),
      );
    }

    _initialized = true;
  }

  static void updateSettings({required bool sound, required bool vibrate}) {
    _soundEnabled = sound;
    _vibrateEnabled = vibrate;
  }

  /// Update the ongoing notification with session counts + server info.
  static Future<void> updateSticky({
    required int working,
    required int pendingApproval,
    required int pendingReview,
    String serverLabel = '',
  }) async {
    _serverLabel = serverLabel;

    final parts = <String>[];
    if (working > 0) parts.add('$working working');
    if (pendingApproval > 0) parts.add('$pendingApproval pending');
    if (pendingReview > 0) parts.add('$pendingReview completed');
    final title = parts.isNotEmpty
        ? 'cc-monitor: ${parts.join(' | ')}'
        : 'cc-monitor';

    final subtitle = serverLabel.isNotEmpty
        ? 'Connected to: $serverLabel'
        : 'No server connected';

    await _plugin.show(
      _stickyNotificationId,
      title,
      subtitle,
      NotificationDetails(
        android: AndroidNotificationDetails(
          _channelStickyId,
          _channelStickyName,
          icon: '@mipmap/ic_launcher',
          ongoing: true,
          autoCancel: false,
          showWhen: false,
          importance: Importance.low,
          priority: Priority.low,
          color: const Color(0xFF22C55E),
          actions: _buildActions(working, pendingApproval, pendingReview),
        ),
      ),
    );
  }

  static List<AndroidNotificationAction> _buildActions(
    int working,
    int pendingApproval,
    int pendingReview,
  ) {
    return [
      AndroidNotificationAction(
        'action_working',
        '$working working',
        showsUserInterface: true,
        cancelNotification: false,
        titleColor: const Color(0xFF58A6FF),
      ),
      AndroidNotificationAction(
        'action_approval',
        '$pendingApproval pending',
        showsUserInterface: true,
        cancelNotification: false,
        titleColor: const Color(0xFFD97706),
      ),
      AndroidNotificationAction(
        'action_completed',
        '$pendingReview completed',
        showsUserInterface: true,
        cancelNotification: false,
        titleColor: const Color(0xFF22C55E),
      ),
    ];
  }

  /// Remove the sticky notification.
  static Future<void> cancelSticky() async {
    await _plugin.cancel(_stickyNotificationId);
  }

  /// Fire an alert notification for a state transition.
  static Future<void> showAlert({
    required String sessionName,
    required String state,
  }) async {
    const stateLabels = {
      'pending_approval': ['⚠ Approval Needed', 'Claude needs permission to proceed'],
      'pending_review': ['✅ Response Ready', 'Claude finished — review the output'],
      'all_done': ['🏁 Session Ended', 'Claude Code session completed'],
    };

    final label = stateLabels[state] ?? ['State Change', 'Session is now $state'];
    final id = DateTime.now().millisecondsSinceEpoch % 100000;

    await _plugin.show(
      id,
      label[0],
      '$sessionName · ${label[1]}',
      NotificationDetails(
        android: AndroidNotificationDetails(
          _channelAlertId,
          _channelAlertName,
          icon: '@mipmap/ic_launcher',
          importance: Importance.high,
          priority: Priority.high,
          playSound: _soundEnabled,
          enableVibration: _vibrateEnabled,
          vibrationPattern: _vibrateEnabled
              ? Int64List.fromList([0, 300, 200, 300])
              : null,
        ),
      ),
    );
  }

  static void _onTap(NotificationResponse response) {}
}
