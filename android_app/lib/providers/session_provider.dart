import 'dart:async';
import 'package:flutter/foundation.dart';
import '../models/session.dart';
import '../services/api_client.dart';
import '../services/sse_client.dart';

class SessionProvider extends ChangeNotifier {
  final ApiClient _api;
  SseClient? _sseClient;
  Timer? _heartbeatTimer;

  List<Session> _active = [];
  List<Session> _complete = [];
  List<Session> _archived = [];
  bool _loading = true;
  bool _connected = false;

  List<Session> get active => List.unmodifiable(_active);
  List<Session> get complete => List.unmodifiable(_complete);
  List<Session> get archived => List.unmodifiable(_archived);
  bool get loading => _loading;
  bool get connected => _connected;

  SessionProvider(this._api);

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
      if (type == 'state_update') {
        final session = Session.fromJson(event);
        _upsert(session);
      } else if (type == 'device_update') {
        // A device was paired or revoked — verify our token is still valid
        _checkTokenValid();
      }
    }, onError: (_) {
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

  Future<void> _checkTokenValid() async {
    try {
      final resp = await _api.get('/api/auth/token/info');
      if (resp.statusCode == 401) {
        _connected = false;
        _clear();
        notifyListeners();
      }
    } catch (_) {
      // Server unreachable — keep current state
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
