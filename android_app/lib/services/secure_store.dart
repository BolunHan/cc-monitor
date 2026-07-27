import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStore {
  static const _keyToken = 'cc_monitor_token';
  static const _keyHost = 'cc_monitor_host';
  static const _keyPort = 'cc_monitor_port';
  static const _keyCertFingerprint = 'cc_monitor_cert_sha256';

  final FlutterSecureStorage _storage;

  SecureStore() : _storage = const FlutterSecureStorage();

  Future<void> savePairing({
    required String token,
    required String host,
    required int port,
    required String certSha256,
  }) async {
    await Future.wait([
      _storage.write(key: _keyToken, value: token),
      _storage.write(key: _keyHost, value: host),
      _storage.write(key: _keyPort, value: port.toString()),
      _storage.write(key: _keyCertFingerprint, value: certSha256),
    ]);
  }

  Future<Map<String, String?>?> loadPairing() async {
    final token = await _storage.read(key: _keyToken);
    if (token == null) return null;
    return {
      'token': token,
      'host': await _storage.read(key: _keyHost),
      'port': await _storage.read(key: _keyPort),
      'cert_sha256': await _storage.read(key: _keyCertFingerprint),
    };
  }

  Future<void> updateToken(String token) async {
    await _storage.write(key: _keyToken, value: token);
  }

  Future<void> clear() async {
    await _storage.deleteAll();
  }

  bool get isConfigured => _storage.containsKey(key: _keyToken) is Future;
}
