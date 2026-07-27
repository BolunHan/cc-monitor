import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import 'secure_store.dart';

const _tag = 'cc-monitor:api';

class ApiClient {
  final SecureStore _store;
  late final Dio _dio;
  String? _token;
  bool _configured = false;

  ApiClient({required SecureStore store}) : _store = store {
    _dio = Dio(BaseOptions(
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 30),
      validateStatus: (status) => status != null && status < 500,
    ));

    _dio.interceptors.add(AuthInterceptor(this));
    _dio.interceptors.add(LogInterceptor(
      logPrint: (o) => debugPrint('[$_tag] $o'),
      requestBody: false,
      responseBody: false,
    ));
  }

  Dio get dio => _dio;

  bool get isConfigured => _configured;

  Future<bool> configureFromStore() async {
    final pairing = await _store.loadPairing();
    if (pairing == null) {
      debugPrint('[$_tag] No stored pairing found');
      return false;
    }

    _token = pairing['token'];

    final host = pairing['host']!;
    final port = int.parse(pairing['port']!);
    _dio.options.baseUrl = 'https://$host:$port';
    debugPrint('[$_tag] Configured: $host:$port (token: ${_token!.substring(0, 8)}...)');

    // Bypass cert validation for self-signed certs
    (_dio.httpClientAdapter as dynamic).onHttpClientCreate = (HttpClient client) {
      client.badCertificateCallback = (cert, host, port) => true;
    };

    _configured = true;
    return true;
  }

  Future<Response> get(String path) => _dio.get(path);
  Future<Response> post(String path, {dynamic data}) =>
      _dio.post(path, data: data);
  Future<Response> delete(String path) => _dio.delete(path);
}

class AuthInterceptor extends Interceptor {
  final ApiClient _client;

  AuthInterceptor(this._client);

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    if (_client._token != null) {
      options.headers['Authorization'] = 'Bearer ${_client._token}';
    }
    handler.next(options);
  }
}
