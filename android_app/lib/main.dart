import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app_theme.dart';
import 'services/api_client.dart';
import 'services/secure_store.dart';
import 'services/pairing_service.dart';
import 'providers/session_provider.dart';
import 'providers/pairing_provider.dart';
import 'screens/dashboard_screen.dart';
import 'screens/session_detail_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/server_picker_screen.dart';
import 'screens/pairing_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

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
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
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
    _configureFuture = widget.apiClient.configureFromStore().then((_) {
      return widget.apiClient.isConfigured;
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

        if (snapshot.data == true) {
          return const DashboardScreen();
        }

        return const ServerPickerScreen();
      },
    );
  }
}
