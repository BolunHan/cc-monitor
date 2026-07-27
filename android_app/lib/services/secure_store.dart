import 'dart:convert';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class ServerEntry {
  final String host;
  final int port;
  final String token;
  final String certSha256;
  final String clientId;

  const ServerEntry({
    required this.host,
    required this.port,
    required this.token,
    required this.certSha256,
    required this.clientId,
  });

  String get displayId => clientId.length >= 8 ? clientId.substring(0, 8) : clientId;

  Map<String, dynamic> toJson() => {
        'host': host, 'port': port.toString(), 'token': token,
        'cert_sha256': certSha256, 'client_id': clientId,
      };

  factory ServerEntry.fromJson(Map<String, dynamic> json) {
    return ServerEntry(
      host: json['host'] as String,
      port: int.parse(json['port'] as String),
      token: json['token'] as String,
      certSha256: json['cert_sha256'] as String? ?? '',
      clientId: json['client_id'] as String? ?? '',
    );
  }
}

class SecureStore {
  static const _keyServers = 'cc_monitor_servers';
  static const _keyClientId = 'cc_monitor_client_id';
  static const _keyActive = 'cc_monitor_active';

  final FlutterSecureStorage _storage;
  SecureStore() : _storage = const FlutterSecureStorage();

  // ---- client ID ----

  Future<String> getClientId() async {
    var cid = await _storage.read(key: _keyClientId);
    if (cid == null || cid.isEmpty) {
      cid = _generateUuid();
      await _storage.write(key: _keyClientId, value: cid);
      debugPrint('[cc-monitor:store] Generated client_id: ${cid.substring(0, 8)}...');
    }
    return cid;
  }

  String _generateUuid() {
    final r = Random.secure();
    final h = List.generate(32, (_) => r.nextInt(16).toRadixString(16)).join();
    return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
  }

  // ---- server list ----

  Future<List<ServerEntry>> getServers() async {
    final raw = await _storage.read(key: _keyServers);
    if (raw == null) return [];
    try {
      return (jsonDecode(raw) as List).map((e) => ServerEntry.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> addServer(ServerEntry entry) async {
    final cid = entry.clientId.isNotEmpty ? entry.clientId : await getClientId();
    final e = ServerEntry(host: entry.host, port: entry.port, token: entry.token, certSha256: entry.certSha256, clientId: cid);
    final servers = await getServers();
    servers.removeWhere((s) => s.host == e.host && s.port == e.port);
    servers.insert(0, e);
    await _storage.write(key: _keyServers, value: jsonEncode(servers.map((s) => s.toJson()).toList()));
    await setActive(e.host, e.port);
  }

  Future<void> removeServer(String host, int port) async {
    final servers = await getServers();
    servers.removeWhere((s) => s.host == host && s.port == port);
    await _storage.write(key: _keyServers, value: jsonEncode(servers.map((s) => s.toJson()).toList()));
  }

  // ---- active server ----

  Future<ServerEntry?> getActive() async {
    final key = await _storage.read(key: _keyActive);
    if (key == null) return (await getServers()).firstOrNull;
    for (final s in await getServers()) {
      if ('${s.host}:${s.port}' == key) return s;
    }
    final servers = await getServers();
    return servers.firstOrNull;
  }

  Future<void> setActive(String host, int port) async {
    await _storage.write(key: _keyActive, value: '$host:$port');
  }

  // ---- legacy ----

  Future<Map<String, String?>?> loadPairing() async {
    final active = await getActive();
    if (active == null) return null;
    return {'token': active.token, 'host': active.host, 'port': active.port.toString(), 'cert_sha256': active.certSha256};
  }

  Future<void> savePairing({required String token, required String host, required int port, required String certSha256}) async {
    final cid = await getClientId();
    await addServer(ServerEntry(host: host, port: port, token: token, certSha256: certSha256, clientId: cid));
  }

  Future<void> updateToken(String token) async {
    final active = await getActive();
    if (active == null) return;
    await addServer(ServerEntry(host: active.host, port: active.port, token: token, certSha256: active.certSha256, clientId: active.clientId));
  }

  Future<void> clear() async => await _storage.deleteAll();
}
