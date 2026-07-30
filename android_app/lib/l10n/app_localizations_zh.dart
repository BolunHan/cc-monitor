// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Chinese (`zh`).
class AppLocalizationsZh extends AppLocalizations {
  AppLocalizationsZh([String locale = 'zh']) : super(locale);

  @override
  String get appTitle => 'cc-monitor';

  @override
  String get noSessions => '无会话';

  @override
  String activeTab(Object count) {
    return '活跃 ($count)';
  }

  @override
  String completeTab(Object count) {
    return '已完成 ($count)';
  }

  @override
  String archivedTab(Object count) {
    return '已归档 ($count)';
  }

  @override
  String get disconnectedBanner => '已断开 — 令牌被撤销或服务器不可达。\n从侧边栏移除此服务器。';

  @override
  String get stateWorking => '工作中';

  @override
  String get stateIdle => '空闲';

  @override
  String get statePendingApproval => '等待批准';

  @override
  String get statePendingReview => '等待审阅';

  @override
  String get stateAllDone => '全部完成';

  @override
  String get stateArchived => '已归档';

  @override
  String get timeJustNow => '刚刚';

  @override
  String timeMinutesAgo(Object n) {
    return '$n分钟前';
  }

  @override
  String timeHoursAgo(Object n) {
    return '$n小时前';
  }

  @override
  String timeDaysAgo(Object n) {
    return '$n天前';
  }

  @override
  String sseAlive(Object count) {
    return 'SSE 已连接 | $count 个事件 | 点击查看日志';
  }

  @override
  String get sseDisconnected => 'SSE 已断开 | 点击查看日志';

  @override
  String eventLogTitle(Object filtered, Object total) {
    return 'SSE 事件日志 ($filtered/$total)';
  }

  @override
  String get eventLogEmpty => '无事件 — 等待 SSE…';

  @override
  String get eventLogLevel => '级别：';

  @override
  String get eventLogConnected => '已连接';

  @override
  String get eventLogDisconnected => '已断开';

  @override
  String get settingsTitle => '设置';

  @override
  String get settingsServer => '服务器';

  @override
  String get settingsTokenStatus => '令牌状态';

  @override
  String get settingsTokenValid => '有效';

  @override
  String settingsTokenExpires(Object date) {
    return '过期时间：$date';
  }

  @override
  String get settingsRotate => '刷新';

  @override
  String get settingsPairNew => '配对新服务器';

  @override
  String get settingsForget => '忘记服务器';

  @override
  String get settingsForgetDesc => '清除所有配对数据';

  @override
  String get settingsNotifications => '通知';

  @override
  String get settingsSound => '声音';

  @override
  String get settingsSoundDesc => '提醒时播放声音';

  @override
  String get settingsVibration => '振动';

  @override
  String get settingsVibrationDesc => '提醒时振动';

  @override
  String get settingsAbout => 'cc-monitor 应用';

  @override
  String get settingsLanguage => '语言';

  @override
  String get settingsLanguageSystem => '跟随系统';

  @override
  String get settingsServers => '服务器';

  @override
  String get settingsActive => '活跃';

  @override
  String get settingsInactive => '未连接';

  @override
  String get settingsDelete => '移除';

  @override
  String get connectTitle => '连接服务器';

  @override
  String get connectScanQr => '扫描二维码';

  @override
  String get connectManual => '手动输入';

  @override
  String get connectNoServers => '局域网内未发现 cc-monitor 服务器';

  @override
  String get connectScanAgain => '重新扫描';

  @override
  String get connectManualTitle => '手动输入';

  @override
  String get connectServerIp => '服务器 IP';

  @override
  String get connectPort => '端口';

  @override
  String get connectToken => '令牌';

  @override
  String get connectCancel => '取消';

  @override
  String get connectConnect => '连接';

  @override
  String get connectingTitle => '连接中';

  @override
  String get pairingCodeLabel => '配对码';

  @override
  String get verifyCodeHint => '在 Web 控制台验证此代码';

  @override
  String get scanQrTitle => '扫描二维码';

  @override
  String get scanFound => '已找到！正在打开…';

  @override
  String get scanHint => '将摄像头对准 Web 控制台显示的二维码';

  @override
  String get sessionTitle => '会话';

  @override
  String get sessionNotFound => '未找到会话';

  @override
  String get sessionId => '会话 ID';

  @override
  String get sessionUid => 'UID';

  @override
  String get sessionState => '状态';

  @override
  String get sessionCwd => '工作目录';

  @override
  String get sessionLastEvent => '最近事件';

  @override
  String get sessionDetail => '详情';

  @override
  String get sessionUpdated => '更新时间';

  @override
  String get archive => '归档';

  @override
  String get unarchive => '取消归档';

  @override
  String get markComplete => '标记完成';

  @override
  String get servers => '服务器';

  @override
  String get noServersPaired => '无已配对服务器';

  @override
  String get addServer => '添加服务器';
}
