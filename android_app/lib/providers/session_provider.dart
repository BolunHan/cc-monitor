import 'package:flutter/foundation.dart';
import '../models/session.dart';
import '../services/api_client.dart';
import '../services/sse_client.dart';

class SessionProvider extends ChangeNotifier {
  final ApiClient _api;
  SseClient? _sseClient;

  List<Session> _active = [];
  List<Session> _complete = [];
  List<Session> _archived = [];
  bool _loading = true;

  List<Session> get active => List.unmodifiable(_active);
  List<Session> get complete => List.unmodifiable(_complete);
  List<Session> get archived => List.unmodifiable(_archived);
  bool get loading => _loading;

  SessionProvider(this._api);

  Future<void> loadSessions() async {
    _loading = true;
    notifyListeners();

    try {
      final resp = await _api.get('/api/status');
      final sessions = (resp.data['sessions'] as List)
          .map((j) => Session.fromJson(j as Map<String, dynamic>))
          .toList();
      _categorize(sessions);
    } catch (_) {
      // Offline or unauthenticated — keep existing data
    }

    _loading = false;
    notifyListeners();
  }

  void connectSse() {
    _sseClient = SseClient(_api);
    _sseClient!.connect().listen((event) {
      if (event['_event_type'] == 'state_update') {
        final session = Session.fromJson(event);
        _upsert(session);
      }
    });
    // Load initial data once connected
    loadSessions();
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
    _sseClient?.disconnect();
    super.dispose();
  }
}
