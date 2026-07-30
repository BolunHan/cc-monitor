import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';

import 'app_theme.dart';
import 'services/api_client.dart';
import 'services/notification_service.dart';
import 'services/secure_store.dart';
import 'services/pairing_service.dart';
import 'providers/session_provider.dart';
import 'providers/pairing_provider.dart';
import 'screens/dashboard_screen.dart';
import 'screens/session_detail_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/server_picker_screen.dart';
import 'screens/pairing_screen.dart';

const _tag = 'cc-monitor';

void main() async {
  debugPrint = (message, {wrapWidth}) {
    debugPrintSynchronously('[$_tag] $message', wrapWidth: wrapWidth);
  };

  debugPrint('=== cc-monitor app starting ===');
  WidgetsFlutterBinding.ensureInitialized();

  // Init notifications (must await for channels to be created)
  await NotificationService.init();

  final secureStore = SecureStore();
  final apiClient = ApiClient(store: secureStore);
  final pairingService = PairingService(apiClient, secureStore);

  runApp(CCMonitorApp(
    secureStore: secureStore,
    apiClient: apiClient,
    pairingService: pairingService,
  ));
}

class CCMonitorApp extends StatelessWidget {
  final SecureStore secureStore;
  final ApiClient apiClient;
  final PairingService pairingService;

  const CCMonitorApp({
    super.key,
    required this.secureStore,
    required this.apiClient,
    required this.pairingService,
  });

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        Provider.value(value: secureStore),
        Provider.value(value: apiClient),
        Provider.value(value: pairingService),
        ChangeNotifierProvider(create: (_) => SessionProvider(apiClient)),
        ChangeNotifierProvider(create: (_) => PairingProvider()),
      ],
      child: MaterialApp(
        title: 'cc-monitor',
        debugShowCheckedModeBanner: false,
        themeMode: ThemeMode.system,
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        supportedLocales: const [Locale('en'), Locale('zh')],
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        home: _StartupGate(
          apiClient: apiClient,
        ),
        onGenerateRoute: (settings) {
          switch (settings.name) {
            case '/':
              return MaterialPageRoute(
                builder: (_) => const DashboardScreen(),
              );
            case '/session':
              final sessionId = settings.arguments as String;
              return MaterialPageRoute(
                builder: (_) => SessionDetailScreen(sessionId: sessionId),
              );
            case '/settings':
              return MaterialPageRoute(
                builder: (_) => const SettingsScreen(),
              );
            case '/servers':
              return MaterialPageRoute(
                builder: (_) => const ServerPickerScreen(),
              );
            case '/pair':
              return MaterialPageRoute(
                builder: (_) => const PairingScreen(),
              );
            default:
              return MaterialPageRoute(
                builder: (_) => const DashboardScreen(),
              );
          }
        },
      ),
    );
  }
}

class _StartupGate extends StatefulWidget {
  final ApiClient apiClient;
  const _StartupGate({required this.apiClient});

  @override
  State<_StartupGate> createState() => _StartupGateState();
}

class _StartupGateState extends State<_StartupGate> {
  late Future<bool> _configureFuture;

  @override
  void initState() {
    super.initState();
    debugPrint('StartupGate: checking stored pairing...');
    _configureFuture = widget.apiClient.configureFromStore().then((configured) {
      debugPrint('StartupGate: stored pairing found=$configured');
      return configured;
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<bool>(
      future: _configureFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        debugPrint('StartupGate build: hasError=${snapshot.hasError} data=${snapshot.data} error=${snapshot.error}');

        if (snapshot.hasError) {
          debugPrint('StartupGate: error loading pairing — ${snapshot.error}');
        }

        if (snapshot.data == true) {
          return const DashboardScreen();
        }

        return const ServerPickerScreen();
      },
    );
  }
}
