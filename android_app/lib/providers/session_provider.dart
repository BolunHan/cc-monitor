import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/session.dart';
import '../services/api_client.dart';
import '../services/sse_client.dart';
import '../services/secure_store.dart';

class SessionProvider extends ChangeNotifier {
  final ApiClient _api;
  SseClient? _sseClient;
  Timer? _heartbeatTimer;

  List<Session> _active = [];
  List<Session> _complete = [];
  List<Session> _archived = [];
  bool _loading = true;
  bool _connected = false;

  // SSE event log
  final List<SseEventEntry> _eventLog = [];
  static const int _maxEventLog = 200;

  // Log level filter
  LogLevel _logLevel = LogLevel.info;

  List<Session> get active => List.unmodifiable(_active);
  List<Session> get complete => List.unmodifiable(_complete);
  List<Session> get archived => List.unmodifiable(_archived);
  bool get loading => _loading;
  bool get connected => _connected;
  LogLevel get logLevel => _logLevel;
  List<SseEventEntry> get eventLog => List.unmodifiable(_eventLog);

  /// Filtered event log (respects current log level).
  List<SseEventEntry> get filteredEventLog =>
      _eventLog.where((e) => _logLevel.shouldShow(e.level)).toList();

  SessionProvider(this._api);

  Future<void> setLogLevel(LogLevel level) async {
    _logLevel = level;
    notifyListeners();
  }

  void _logEvent(String type, String detail, {LogLevel level = LogLevel.info}) {
    _eventLog.insert(0, SseEventEntry(DateTime.now(), type, detail, level));
    if (_eventLog.length > _maxEventLog) {
      _eventLog.removeRange(_maxEventLog, _eventLog.length);
    }
    // Only notify if the event is visible at current level
    if (_logLevel.shouldShow(level)) {
      notifyListeners();
    }
  }

  Future<void> loadSessions() async {
    if (!_api.isConfigured) return;
    _loading = true;
    notifyListeners();

    try {
      final resp = await _api.get('/api/status');
      if (resp.statusCode == 200) {
        final sessions = (resp.data['sessions'] as List)
            .map((j) => Session.fromJson(j as Map<String, dynamic>))
            .toList();
        _categorize(sessions);
        _connected = true;
      } else if (resp.statusCode == 401) {
        _connected = false;
        _clear();
      }
    } catch (_) {
      _connected = false;
    }

    _loading = false;
    notifyListeners();
  }

  void connectSse() {
    if (!_api.isConfigured) return;
    _sseClient = SseClient(_api);
    _sseClient!.connect().listen((event) {
      final type = event['_event_type'] as String?;
      final level = _eventLevel(type);
      _logEvent(type ?? 'unknown', _describeEvent(type, event), level: level);
      if (type == 'state_update') {
        final session = Session.fromJson(event);
        _upsert(session);
        _connected = true;
      } else if (type == 'heartbeat') {
        _connected = true;
      } else if (type == 'device_update') {
        _logEvent('ACTION', 'device_update → checking token…', level: LogLevel.info);
        _checkTokenValid();
      }
    }, onError: (_) {
      _logEvent('ERROR', 'SSE stream error', level: LogLevel.error);
      _connected = false;
      notifyListeners();
    });
    loadSessions();
    _startHeartbeat();
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 10), (_) async {
      if (!_api.isConfigured) return;
      try {
        final resp = await _api.get('/api/version');
        if (resp.statusCode == 401) {
          _connected = false;
          _clear();
          notifyListeners();
        } else {
          _connected = true;
          notifyListeners();
        }
      } catch (_) {
        _connected = false;
        notifyListeners();
      }
    });
  }

  LogLevel _eventLevel(String? type) {
    return switch (type) {
      'heartbeat' => LogLevel.debug,
      'state_update' => LogLevel.info,
      'device_update' => LogLevel.info,
      'pairing_request' => LogLevel.info,
      'pairing_resolved' => LogLevel.info,
      _ => LogLevel.info,
    };
  }

  String _describeEvent(String? type, Map<String, dynamic> event) {
    if (type == 'state_update') {
      return 'session: ${event['session_id']?.toString().substring(0, 8) ?? '?'} → ${event['state'] ?? '?'}';
    }
    if (type == 'heartbeat') return '♥';
    if (type == 'device_update') return 'device list changed';
    return event.toString();
  }

  Future<void> _checkTokenValid() async {
    try {
      final resp = await _api.get('/api/auth/token/info');
      if (resp.statusCode == 401) {
        _logEvent('ACTION', 'token REVOKED (401) → disconnecting', level: LogLevel.warning);
        _connected = false;
        _clear();
        notifyListeners();
      } else {
        _logEvent('ACTION', 'token valid (${resp.statusCode})', level: LogLevel.debug);
      }
    } catch (e) {
      _logEvent('ACTION', 'token check failed: $e', level: LogLevel.error);
    }
  }

  void _clear() {
    _active = [];
    _complete = [];
    _archived = [];
    _sseClient?.disconnect();
    _sseClient = null;
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
  }

  Future<void> archiveSession(String sessionId) async {
    await _api.post('/api/session/$sessionId/archive');
    await loadSessions();
  }

  Future<void> unarchiveSession(String sessionId) async {
    await _api.post('/api/session/$sessionId/unarchive');
    await loadSessions();
  }

  Future<void> markComplete(String sessionId) async {
    await _api.post('/api/session/$sessionId/complete');
    await loadSessions();
  }

  void _upsert(Session session) {
    _active.removeWhere((s) => s.sessionId == session.sessionId);
    _complete.removeWhere((s) => s.sessionId == session.sessionId);
    _archived.removeWhere((s) => s.sessionId == session.sessionId);

    if (session.archived) {
      _archived.add(session);
    } else if (session.isComplete) {
      _complete.add(session);
    } else {
      _active.add(session);
    }

    _active.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    _complete.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    _archived.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));

    notifyListeners();
  }

  void _categorize(List<Session> sessions) {
    _active = sessions.where((s) => s.isActive).toList()
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    _complete = sessions.where((s) => s.isComplete).toList()
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    _archived = sessions.where((s) => s.archived).toList()
      ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
  }

  @override
  void dispose() {
    _heartbeatTimer?.cancel();
    _sseClient?.disconnect();
    super.dispose();
  }
}

class SseEventEntry {
  final DateTime time;
  final String type;
  final String detail;
  final LogLevel level;
  SseEventEntry(this.time, this.type, this.detail, this.level);
}
