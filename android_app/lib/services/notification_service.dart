import 'dart:async';
import 'package:flutter/services.dart';

class NotificationService {
  static const _channel = MethodChannel('cc_monitor/notifications');

  static final _actionTapController = StreamController<String>.broadcast();
  static Stream<String> get onActionTap => _actionTapController.stream;

  static bool _soundEnabled = true;
  static bool _vibrateEnabled = true;

  static bool get soundEnabled => _soundEnabled;
  static bool get vibrateEnabled => _vibrateEnabled;

  static Future<bool> requestPermission() async {
    final granted = await _channel.invokeMethod<bool>('requestPermission');
    return granted ?? false;
  }

  static Future<void> init() async {
    _channel.setMethodCallHandler((call) async {
      if (call.method == 'onActionTap') {
        _actionTapController.add(call.arguments as String);
      }
    });

    // Request notification permission before starting service
    await _channel.invokeMethod('requestPermission');
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
