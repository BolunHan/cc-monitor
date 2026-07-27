import 'package:flutter/material.dart';
import 'app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const CCMonitorApp());
}

class CCMonitorApp extends StatelessWidget {
  const CCMonitorApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'cc-monitor',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      home: const Scaffold(
        body: Center(child: Text('cc-monitor')),
      ),
    );
  }
}
