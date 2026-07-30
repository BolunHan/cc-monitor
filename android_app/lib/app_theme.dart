import 'package:flutter/material.dart';

class AppTheme {
  // cc-monitor brand palette — dark
  static const _bgDark = Color(0xFF0D1117);
  static const _surfaceDark = Color(0xFF161B22);
  static const _textDark = Color(0xFFE6EDF3);
  static const _mutedDark = Color(0xFF8B949E);
  static const _borderDark = Color(0xFF30363D);

  // cc-monitor brand palette — light
  static const _bgLight = Color(0xFFF6F8FA);
  static const _surfaceLight = Color(0xFFFFFFFF);
  static const _textLight = Color(0xFF1A1D27);
  static const _mutedLight = Color(0xFF656D76);
  static const _borderLight = Color(0xFFD0D7DE);

  // Shared accent colors
  static const _accent = Color(0xFF22C55E);
  static const _amber = Color(0xFFD97706);
  static const _red = Color(0xFFDA3633);
  static const _blue = Color(0xFF58A6FF);

  static ThemeData get dark => ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        colorScheme: const ColorScheme.dark(
          primary: _accent,
          secondary: _blue,
          surface: _surfaceDark,
          error: _red,
          onPrimary: _bgDark,
          onSecondary: _bgDark,
          onSurface: _textDark,
          onError: _textDark,
        ),
        scaffoldBackgroundColor: _bgDark,
        appBarTheme: const AppBarTheme(
          backgroundColor: _surfaceDark,
          foregroundColor: _textDark,
          elevation: 0,
          scrolledUnderElevation: 1,
          centerTitle: false,
          titleTextStyle: TextStyle(
            color: _textDark, fontSize: 18, fontWeight: FontWeight.w600,
          ),
        ),
        cardTheme: CardThemeData(
          color: _surfaceDark,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: const BorderSide(color: _borderDark, width: 0.5),
          ),
          margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        ),
        tabBarTheme: TabBarThemeData(
          labelColor: _textDark,
          unselectedLabelColor: _mutedDark,
          indicatorColor: _accent,
          dividerColor: _borderDark,
        ),
        drawerTheme: const DrawerThemeData(
          backgroundColor: _surfaceDark,
        ),
        dividerColor: _borderDark,
        iconTheme: const IconThemeData(color: _mutedDark),
        textTheme: const TextTheme(
          bodySmall: TextStyle(color: _mutedDark, fontSize: 12),
          bodyMedium: TextStyle(color: _textDark, fontSize: 14),
        ),
        snackBarTheme: SnackBarThemeData(
          backgroundColor: _surfaceDark,
          contentTextStyle: const TextStyle(color: _textDark),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          behavior: SnackBarBehavior.floating,
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: _accent,
          foregroundColor: _bgDark,
        ),
      );

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        brightness: Brightness.light,
        colorScheme: const ColorScheme.light(
          primary: _accent,
          secondary: _blue,
          surface: _surfaceLight,
          error: _red,
          onPrimary: _surfaceLight,
          onSecondary: _surfaceLight,
          onSurface: _textLight,
          onError: _surfaceLight,
        ),
        scaffoldBackgroundColor: _bgLight,
        appBarTheme: const AppBarTheme(
          backgroundColor: _surfaceLight,
          foregroundColor: _textLight,
          elevation: 0,
          scrolledUnderElevation: 1,
          centerTitle: false,
          titleTextStyle: TextStyle(
            color: _textLight, fontSize: 18, fontWeight: FontWeight.w600,
          ),
        ),
        cardTheme: CardThemeData(
          color: _surfaceLight,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: const BorderSide(color: _borderLight, width: 0.5),
          ),
          margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        ),
        tabBarTheme: TabBarThemeData(
          labelColor: _textLight,
          unselectedLabelColor: _mutedLight,
          indicatorColor: _accent,
          dividerColor: _borderLight,
        ),
        drawerTheme: const DrawerThemeData(
          backgroundColor: _surfaceLight,
        ),
        dividerColor: _borderLight,
        iconTheme: const IconThemeData(color: _mutedLight),
        textTheme: const TextTheme(
          bodySmall: TextStyle(color: _mutedLight, fontSize: 12),
          bodyMedium: TextStyle(color: _textLight, fontSize: 14),
        ),
        snackBarTheme: SnackBarThemeData(
          backgroundColor: _surfaceLight,
          contentTextStyle: const TextStyle(color: _textLight),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          behavior: SnackBarBehavior.floating,
        ),
        floatingActionButtonTheme: const FloatingActionButtonThemeData(
          backgroundColor: _accent,
          foregroundColor: _surfaceLight,
        ),
      );

  // Accent colors for state badges across the app
  static Color stateColor(String state) {
    return switch (state) {
      'working' => _amber,
      'pending_review' => _blue,
      'pending_approval' => _red,
      'idle' => _mutedDark,
      'all_done' => _accent,
      _ => _mutedDark,
    };
  }

  static Color stateBgColor(String state) {
    return switch (state) {
      'working' => _amber.withAlpha(30),
      'pending_review' => _blue.withAlpha(30),
      'pending_approval' => _red.withAlpha(30),
      'idle' => _mutedDark.withAlpha(20),
      'all_done' => _accent.withAlpha(30),
      _ => _mutedDark.withAlpha(20),
    };
  }
}
