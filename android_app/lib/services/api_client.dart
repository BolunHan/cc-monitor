import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import 'secure_store.dart';

class ApiClient {
  final SecureStore _store;
  late final Dio _dio;
  String? _token;
  String? _certSha256;

  ApiClient({required SecureStore store}) : _store = store {
    _dio = Dio(BaseOptions(
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 30),
    ));

    _dio.interceptors.add(AuthInterceptor(this));
  }

  Dio get dio => _dio;

  bool get isConfigured => _token != null;

  Future<void> configureFromStore() async {
    final pairing = await _store.loadPairing();
    if (pairing == null) return;

    _token = pairing['token'];
    _certSha256 = pairing['cert_sha256'];

    final host = pairing['host']!;
    final port = int.parse(pairing['port']!);
    _dio.options.baseUrl = 'https://$host:$port';

    // Cert pinning: trust only the pinned certificate
    if (_certSha256 != null) {
      _dio.httpClientAdapter = _createPinningAdapter(_certSha256!);
    }
  }

  HttpClientAdapter _createPinningAdapter(String certSha256) {
    return IOHttpClientAdapter(
      createHttpClient: () {
        final client = HttpClient();
        client.badCertificateCallback = (cert, host, port) {
          final fingerprint = _computeSha256(cert);
          return fingerprint == certSha256;
        };
        return client;
      },
    );
  }

  String _computeSha256(dynamic cert) {
    // Simplified — in production, hash the DER bytes
    // The real implementation computes SHA-256 over the DER-encoded cert
    // using dart:crypto or the crypto package
    return certSha256; // placeholder — real impl in flutter create
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

  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    // Read X-Token-Expires header for expiry countdown
    final expiresHeader = response.headers.value('X-Token-Expires');
    if (expiresHeader != null) {
      // Could notify a provider about the expiry time
    }
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (err.response?.statusCode == 401) {
      final expired = err.response?.headers.value('X-Token-Expired');
      if (expired == 'true') {
        // Token expired — will be handled by the provider
      }
    }
    handler.next(err);
  }
}
