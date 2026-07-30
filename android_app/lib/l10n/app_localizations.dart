import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_zh.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
      : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('zh')
  ];

  /// No description provided for @appTitle.
  ///
  /// In en, this message translates to:
  /// **'cc-monitor'**
  String get appTitle;

  /// No description provided for @noSessions.
  ///
  /// In en, this message translates to:
  /// **'No sessions'**
  String get noSessions;

  /// No description provided for @activeTab.
  ///
  /// In en, this message translates to:
  /// **'Active ({count})'**
  String activeTab(Object count);

  /// No description provided for @completeTab.
  ///
  /// In en, this message translates to:
  /// **'Complete ({count})'**
  String completeTab(Object count);

  /// No description provided for @archivedTab.
  ///
  /// In en, this message translates to:
  /// **'Archived ({count})'**
  String archivedTab(Object count);

  /// No description provided for @disconnectedBanner.
  ///
  /// In en, this message translates to:
  /// **'Disconnected — token revoked or server unreachable.\nRemove this server from the sidebar.'**
  String get disconnectedBanner;

  /// No description provided for @stateWorking.
  ///
  /// In en, this message translates to:
  /// **'working'**
  String get stateWorking;

  /// No description provided for @stateIdle.
  ///
  /// In en, this message translates to:
  /// **'idle'**
  String get stateIdle;

  /// No description provided for @statePendingApproval.
  ///
  /// In en, this message translates to:
  /// **'pending approval'**
  String get statePendingApproval;

  /// No description provided for @statePendingReview.
  ///
  /// In en, this message translates to:
  /// **'pending review'**
  String get statePendingReview;

  /// No description provided for @stateAllDone.
  ///
  /// In en, this message translates to:
  /// **'all done'**
  String get stateAllDone;

  /// No description provided for @stateArchived.
  ///
  /// In en, this message translates to:
  /// **'archived'**
  String get stateArchived;

  /// No description provided for @timeJustNow.
  ///
  /// In en, this message translates to:
  /// **'just now'**
  String get timeJustNow;

  /// No description provided for @timeMinutesAgo.
  ///
  /// In en, this message translates to:
  /// **'{n}m ago'**
  String timeMinutesAgo(Object n);

  /// No description provided for @timeHoursAgo.
  ///
  /// In en, this message translates to:
  /// **'{n}h ago'**
  String timeHoursAgo(Object n);

  /// No description provided for @timeDaysAgo.
  ///
  /// In en, this message translates to:
  /// **'{n}d ago'**
  String timeDaysAgo(Object n);

  /// No description provided for @sseAlive.
  ///
  /// In en, this message translates to:
  /// **'SSE alive | {count} events | tap for log'**
  String sseAlive(Object count);

  /// No description provided for @sseDisconnected.
  ///
  /// In en, this message translates to:
  /// **'SSE disconnected | tap for log'**
  String get sseDisconnected;

  /// No description provided for @eventLogTitle.
  ///
  /// In en, this message translates to:
  /// **'SSE Event Log ({filtered}/{total})'**
  String eventLogTitle(Object filtered, Object total);

  /// No description provided for @eventLogEmpty.
  ///
  /// In en, this message translates to:
  /// **'No events — waiting for SSE…'**
  String get eventLogEmpty;

  /// No description provided for @eventLogLevel.
  ///
  /// In en, this message translates to:
  /// **'Level:'**
  String get eventLogLevel;

  /// No description provided for @eventLogConnected.
  ///
  /// In en, this message translates to:
  /// **'CONNECTED'**
  String get eventLogConnected;

  /// No description provided for @eventLogDisconnected.
  ///
  /// In en, this message translates to:
  /// **'DISCONNECTED'**
  String get eventLogDisconnected;

  /// No description provided for @settingsTitle.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsTitle;

  /// No description provided for @settingsServer.
  ///
  /// In en, this message translates to:
  /// **'Server'**
  String get settingsServer;

  /// No description provided for @settingsTokenStatus.
  ///
  /// In en, this message translates to:
  /// **'Token Status'**
  String get settingsTokenStatus;

  /// No description provided for @settingsTokenValid.
  ///
  /// In en, this message translates to:
  /// **'Valid'**
  String get settingsTokenValid;

  /// No description provided for @settingsTokenExpires.
  ///
  /// In en, this message translates to:
  /// **'Expires: {date}'**
  String settingsTokenExpires(Object date);

  /// No description provided for @settingsRotate.
  ///
  /// In en, this message translates to:
  /// **'Rotate'**
  String get settingsRotate;

  /// No description provided for @settingsPairNew.
  ///
  /// In en, this message translates to:
  /// **'Pair New Server'**
  String get settingsPairNew;

  /// No description provided for @settingsForget.
  ///
  /// In en, this message translates to:
  /// **'Forget Server'**
  String get settingsForget;

  /// No description provided for @settingsForgetDesc.
  ///
  /// In en, this message translates to:
  /// **'Clear all pairing data'**
  String get settingsForgetDesc;

  /// No description provided for @settingsNotifications.
  ///
  /// In en, this message translates to:
  /// **'Notifications'**
  String get settingsNotifications;

  /// No description provided for @settingsSound.
  ///
  /// In en, this message translates to:
  /// **'Sound'**
  String get settingsSound;

  /// No description provided for @settingsSoundDesc.
  ///
  /// In en, this message translates to:
  /// **'Play sound on alerts'**
  String get settingsSoundDesc;

  /// No description provided for @settingsVibration.
  ///
  /// In en, this message translates to:
  /// **'Vibration'**
  String get settingsVibration;

  /// No description provided for @settingsVibrationDesc.
  ///
  /// In en, this message translates to:
  /// **'Vibrate on alerts'**
  String get settingsVibrationDesc;

  /// No description provided for @settingsAbout.
  ///
  /// In en, this message translates to:
  /// **'cc-monitor App'**
  String get settingsAbout;

  /// No description provided for @settingsLanguage.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get settingsLanguage;

  /// No description provided for @settingsLanguageSystem.
  ///
  /// In en, this message translates to:
  /// **'System default'**
  String get settingsLanguageSystem;

  /// No description provided for @settingsServers.
  ///
  /// In en, this message translates to:
  /// **'Servers'**
  String get settingsServers;

  /// No description provided for @settingsActive.
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get settingsActive;

  /// No description provided for @settingsInactive.
  ///
  /// In en, this message translates to:
  /// **'Inactive'**
  String get settingsInactive;

  /// No description provided for @settingsDelete.
  ///
  /// In en, this message translates to:
  /// **'Forget'**
  String get settingsDelete;

  /// No description provided for @connectTitle.
  ///
  /// In en, this message translates to:
  /// **'Connect to Server'**
  String get connectTitle;

  /// No description provided for @connectScanQr.
  ///
  /// In en, this message translates to:
  /// **'Scan QR Code'**
  String get connectScanQr;

  /// No description provided for @connectManual.
  ///
  /// In en, this message translates to:
  /// **'Manual Entry'**
  String get connectManual;

  /// No description provided for @connectNoServers.
  ///
  /// In en, this message translates to:
  /// **'No cc-monitor servers found on LAN'**
  String get connectNoServers;

  /// No description provided for @connectScanAgain.
  ///
  /// In en, this message translates to:
  /// **'Scan Again'**
  String get connectScanAgain;

  /// No description provided for @connectManualTitle.
  ///
  /// In en, this message translates to:
  /// **'Manual Entry'**
  String get connectManualTitle;

  /// No description provided for @connectServerIp.
  ///
  /// In en, this message translates to:
  /// **'Server IP'**
  String get connectServerIp;

  /// No description provided for @connectPort.
  ///
  /// In en, this message translates to:
  /// **'Port'**
  String get connectPort;

  /// No description provided for @connectToken.
  ///
  /// In en, this message translates to:
  /// **'Token'**
  String get connectToken;

  /// No description provided for @connectCancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get connectCancel;

  /// No description provided for @connectConnect.
  ///
  /// In en, this message translates to:
  /// **'Connect'**
  String get connectConnect;

  /// No description provided for @connectingTitle.
  ///
  /// In en, this message translates to:
  /// **'Connecting'**
  String get connectingTitle;

  /// No description provided for @pairingCodeLabel.
  ///
  /// In en, this message translates to:
  /// **'Pairing Code'**
  String get pairingCodeLabel;

  /// No description provided for @verifyCodeHint.
  ///
  /// In en, this message translates to:
  /// **'Verify this code on the web dashboard'**
  String get verifyCodeHint;

  /// No description provided for @scanQrTitle.
  ///
  /// In en, this message translates to:
  /// **'Scan QR Code'**
  String get scanQrTitle;

  /// No description provided for @scanFound.
  ///
  /// In en, this message translates to:
  /// **'Found! Opening...'**
  String get scanFound;

  /// No description provided for @scanHint.
  ///
  /// In en, this message translates to:
  /// **'Point camera at the QR code shown on the web dashboard'**
  String get scanHint;

  /// No description provided for @sessionTitle.
  ///
  /// In en, this message translates to:
  /// **'Session'**
  String get sessionTitle;

  /// No description provided for @sessionNotFound.
  ///
  /// In en, this message translates to:
  /// **'Session not found'**
  String get sessionNotFound;

  /// No description provided for @sessionId.
  ///
  /// In en, this message translates to:
  /// **'Session ID'**
  String get sessionId;

  /// No description provided for @sessionUid.
  ///
  /// In en, this message translates to:
  /// **'UID'**
  String get sessionUid;

  /// No description provided for @sessionState.
  ///
  /// In en, this message translates to:
  /// **'State'**
  String get sessionState;

  /// No description provided for @sessionCwd.
  ///
  /// In en, this message translates to:
  /// **'CWD'**
  String get sessionCwd;

  /// No description provided for @sessionLastEvent.
  ///
  /// In en, this message translates to:
  /// **'Last Event'**
  String get sessionLastEvent;

  /// No description provided for @sessionDetail.
  ///
  /// In en, this message translates to:
  /// **'Detail'**
  String get sessionDetail;

  /// No description provided for @sessionUpdated.
  ///
  /// In en, this message translates to:
  /// **'Updated'**
  String get sessionUpdated;

  /// No description provided for @archive.
  ///
  /// In en, this message translates to:
  /// **'Archive'**
  String get archive;

  /// No description provided for @unarchive.
  ///
  /// In en, this message translates to:
  /// **'Unarchive'**
  String get unarchive;

  /// No description provided for @markComplete.
  ///
  /// In en, this message translates to:
  /// **'Mark Complete'**
  String get markComplete;

  /// No description provided for @servers.
  ///
  /// In en, this message translates to:
  /// **'Servers'**
  String get servers;

  /// No description provided for @noServersPaired.
  ///
  /// In en, this message translates to:
  /// **'No servers paired'**
  String get noServersPaired;

  /// No description provided for @addServer.
  ///
  /// In en, this message translates to:
  /// **'Add Server'**
  String get addServer;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'zh'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'zh':
      return AppLocalizationsZh();
  }

  throw FlutterError(
      'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
      'an issue with the localizations generation tool. Please file an issue '
      'on GitHub with a reproducible sample app and the gen-l10n configuration '
      'that was used.');
}
