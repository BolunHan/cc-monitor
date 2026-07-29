import 'package:flutter/material.dart';

class AppTheme {
  // cc-monitor brand palette
  static const _bg = Color(0xFF0D1117);
  static const _surface = Color(0xFF161B22);
  static const _accent = Color(0xFF22C55E);
  static const _accentDim = Color(0xFF1A7F3E);
  static const _amber = Color(0xFFD97706);
  static const _red = Color(0xFFDA3633);
  static const _blue = Color(0xFF58A6FF);
  static const _text = Color(0xFFE6EDF3);
  static const _muted = Color(0xFF8B949E);
  static const _border = Color(0xFF30363D);

  static ThemeData get dark => ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: const ColorScheme.dark(
          primary: _accent,
          secondary: _blue,
          surface: _surface,
          error: _red,
          onPrimary: _bg,
          onSecondary: _bg,
          onSurface: _text,
          onError: _text,
        ),
        scaffoldBackgroundColor: _bg,
        appBarTheme: const AppBarTheme(
          backgroundColor: _surface,
          foregroundColor: _text,
          elevation: 0,
          scrolledUnderElevation: 1,
          centerTitle: false,
          titleTextStyle: TextStyle(
            color: _text, fontSize: 18, fontWeight: FontWeight.w600,
          ),
        ),
        cardTheme: CardThemeData(
          color: _surface,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: const BorderSide(color: _border, width: 0.5),
          ),
          margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        ),
        tabBarTheme: TabBarThemeData(
          labelColor: _text,
          unselectedLabelColor: _muted,
          indicatorColor: _accent,
          dividerColor: _border,
        ),
        drawerTheme: const DrawerThemeData(
          backgroundColor: _surface,
        ),
        dividerColor: _border,
        iconTheme: const IconThemeData(color: _muted),
        textTheme: const TextTheme(
          bodySmall: TextStyle(color: _muted, fontSize: 12),
          bodyMedium: TextStyle(color: _text, fontSize: 14),
        ),
        snackBarTheme: SnackBarThemeData(
          backgroundColor: _surface,
          contentTextStyle: const TextStyle(color: _text),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          behavior: SnackBarBehavior.floating,
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: _accent,
          foregroundColor: _bg,
        ),
      );

  // Accent colors for state badges across the app
  static Color stateColor(String state) {
    return switch (state) {
      'working' => _amber,
      'pending_review' => _blue,
      'pending_approval' => _red,
      'idle' => _muted,
      'all_done' => _accent,
      _ => _muted,
    };
  }

  static Color stateBgColor(String state) {
    return switch (state) {
      'working' => _amber.withAlpha(30),
      'pending_review' => _blue.withAlpha(30),
      'pending_approval' => _red.withAlpha(30),
      'idle' => _muted.withAlpha(20),
      'all_done' => _accent.withAlpha(30),
      _ => _muted.withAlpha(20),
    };
  }
}
