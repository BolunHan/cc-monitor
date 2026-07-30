// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'cc-monitor';

  @override
  String get noSessions => 'No sessions';

  @override
  String activeTab(Object count) {
    return 'Active ($count)';
  }

  @override
  String completeTab(Object count) {
    return 'Complete ($count)';
  }

  @override
  String archivedTab(Object count) {
    return 'Archived ($count)';
  }

  @override
  String get disconnectedBanner => 'Disconnected — token revoked or server unreachable.\nRemove this server from the sidebar.';

  @override
  String get stateWorking => 'working';

  @override
  String get stateIdle => 'idle';

  @override
  String get statePendingApproval => 'pending approval';

  @override
  String get statePendingReview => 'pending review';

  @override
  String get stateAllDone => 'all done';

  @override
  String get stateArchived => 'archived';

  @override
  String get timeJustNow => 'just now';

  @override
  String timeMinutesAgo(Object n) {
    return '${n}m ago';
  }

  @override
  String timeHoursAgo(Object n) {
    return '${n}h ago';
  }

  @override
  String timeDaysAgo(Object n) {
    return '${n}d ago';
  }

  @override
  String sseAlive(Object count) {
    return 'SSE alive | $count events | tap for log';
  }

  @override
  String get sseDisconnected => 'SSE disconnected | tap for log';

  @override
  String eventLogTitle(Object filtered, Object total) {
    return 'SSE Event Log ($filtered/$total)';
  }

  @override
  String get eventLogEmpty => 'No events — waiting for SSE…';

  @override
  String get eventLogLevel => 'Level:';

  @override
  String get eventLogConnected => 'CONNECTED';

  @override
  String get eventLogDisconnected => 'DISCONNECTED';

  @override
  String get settingsTitle => 'Settings';

  @override
  String get settingsServer => 'Server';

  @override
  String get settingsTokenStatus => 'Token Status';

  @override
  String get settingsTokenValid => 'Valid';

  @override
  String settingsTokenExpires(Object date) {
    return 'Expires: $date';
  }

  @override
  String get settingsRotate => 'Rotate';

  @override
  String get settingsPairNew => 'Pair New Server';

  @override
  String get settingsForget => 'Forget Server';

  @override
  String get settingsForgetDesc => 'Clear all pairing data';

  @override
  String get settingsNotifications => 'Notifications';

  @override
  String get settingsSound => 'Sound';

  @override
  String get settingsSoundDesc => 'Play sound on alerts';

  @override
  String get settingsVibration => 'Vibration';

  @override
  String get settingsVibrationDesc => 'Vibrate on alerts';

  @override
  String get settingsAbout => 'cc-monitor App';

  @override
  String get connectTitle => 'Connect to Server';

  @override
  String get connectScanQr => 'Scan QR Code';

  @override
  String get connectManual => 'Manual Entry';

  @override
  String get connectNoServers => 'No cc-monitor servers found on LAN';

  @override
  String get connectScanAgain => 'Scan Again';

  @override
  String get connectManualTitle => 'Manual Entry';

  @override
  String get connectServerIp => 'Server IP';

  @override
  String get connectPort => 'Port';

  @override
  String get connectToken => 'Token';

  @override
  String get connectCancel => 'Cancel';

  @override
  String get connectConnect => 'Connect';

  @override
  String get connectingTitle => 'Connecting';

  @override
  String get pairingCodeLabel => 'Pairing Code';

  @override
  String get verifyCodeHint => 'Verify this code on the web dashboard';

  @override
  String get scanQrTitle => 'Scan QR Code';

  @override
  String get scanFound => 'Found! Opening...';

  @override
  String get scanHint => 'Point camera at the QR code shown on the web dashboard';

  @override
  String get sessionTitle => 'Session';

  @override
  String get sessionNotFound => 'Session not found';

  @override
  String get sessionId => 'Session ID';

  @override
  String get sessionUid => 'UID';

  @override
  String get sessionState => 'State';

  @override
  String get sessionCwd => 'CWD';

  @override
  String get sessionLastEvent => 'Last Event';

  @override
  String get sessionDetail => 'Detail';

  @override
  String get sessionUpdated => 'Updated';

  @override
  String get archive => 'Archive';

  @override
  String get unarchive => 'Unarchive';

  @override
  String get markComplete => 'Mark Complete';

  @override
  String get servers => 'Servers';

  @override
  String get noServersPaired => 'No servers paired';

  @override
  String get addServer => 'Add Server';
}
