import 'dart:convert';
import 'package:dio/dio.dart';
import 'api_client.dart';
import 'secure_store.dart';

class PairingService {
  final ApiClient _api;
  final SecureStore _store;

  PairingService(this._api, this._store);

  Future<Map<String, dynamic>> getQrPayload(String host, int port) async {
    final dio = Dio(BaseOptions(
      baseUrl: 'https://$host:$port',
      validateStatus: (_) => true,
    ));
    final resp = await dio.get('/api/auth/pair/qr');
    return resp.data as Map<String, dynamic>;
  }

  Future<bool> confirmQrToken({
    required String host,
    required int port,
    required String token,
    required String deviceName,
  }) async {
    final dio = Dio(BaseOptions(
      baseUrl: 'https://$host:$port',
      validateStatus: (_) => true,
    ));
    final resp = await dio.post(
      '/api/auth/pair/qr/confirm',
      data: {'token': token, 'device_name': deviceName},
    );

    if (resp.statusCode == 200 && resp.data['status'] == 'paired') {
      // Extract cert fingerprint from the QR payload (passed separately)
      // and save everything
      return true;
    }
    return false;
  }

  Future<String?> submitPairingRequest({
    required String host,
    required int port,
    required String deviceName,
  }) async {
    final dio = Dio(BaseOptions(
      baseUrl: 'https://$host:$port',
      validateStatus: (_) => true,
    ));
    final resp = await dio.post(
      '/api/auth/pair/request',
      data: {'device_name': deviceName},
    );

    if (resp.statusCode == 200) {
      return resp.data['request_id'] as String;
    }
    return null;
  }

  Future<Map<String, dynamic>?> pollRequestStatus({
    required String host,
    required int port,
    required String requestId,
  }) async {
    final dio = Dio(BaseOptions(
      baseUrl: 'https://$host:$port',
      validateStatus: (_) => true,
    ));
    final resp = await dio.get(
      '/api/auth/pair/request/$requestId/status',
    );

    if (resp.statusCode == 200) {
      return resp.data as Map<String, dynamic>;
    }
    return null;
  }

  Future<Map<String, dynamic>?> rotateToken() async {
    final resp = await _api.post('/api/auth/token/rotate',
        data: {'device_name': 'Android'});

    if (resp.statusCode == 200) {
      final token = resp.data['token'] as String;
      await _store.updateToken(token);
      return resp.data as Map<String, dynamic>;
    }
    return null;
  }
}
