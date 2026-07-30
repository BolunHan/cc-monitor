import 'dart:io';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:cc_monitor_app/l10n/app_localizations.dart';
import '../services/api_client.dart';
import '../services/secure_store.dart';

/// Create a Dio instance that accepts self-signed certificates.
/// Only used during the pairing handshake — the real ApiClient enforces
/// cert pinning after pairing is complete.
Dio _createPairingDio(String baseUrl) {
  final dio = Dio(BaseOptions(
    baseUrl: baseUrl,
    validateStatus: (_) => true,
    connectTimeout: const Duration(seconds: 5),
    receiveTimeout: const Duration(seconds: 10),
  ));
  // Bypass cert validation for self-signed cert during pairing
  (dio.httpClientAdapter as dynamic).onHttpClientCreate = (HttpClient client) {
    client.badCertificateCallback = (cert, host, port) => true;
  };
  return dio;
}

const _tag = 'cc-monitor:connect';

class ConnectingScreen extends StatefulWidget {
  final String host;
  final int port;
  final String? qrToken;
  final String? certSha256;

  const ConnectingScreen({
    super.key,
    required this.host,
    required this.port,
    this.qrToken,
    this.certSha256,
  });

  @override
  State<ConnectingScreen> createState() => _ConnectingScreenState();
}

class _ConnectingScreenState extends State<ConnectingScreen> {
  final List<String> _log = [];
  String _status = 'Connecting...';
  bool _done = false;
  final String _pairingCode = (Random().nextInt(900000) + 100000).toString();
  final String _deviceName = 'Android';

  @override
  void initState() {
    super.initState();
    _connect();
  }

  void _addLog(String msg) {
    debugPrint('[$_tag] $msg');
    setState(() => _log.add(msg));
  }

  Future<void> _connect() async {
    final baseUrl = 'https://${widget.host}:${widget.port}';
    _addLog('Target: $baseUrl');

    final store = context.read<SecureStore>();
    final clientId = await store.getClientId();
    _addLog('Client ID: ${clientId.substring(0, 8)}...');

    if (widget.qrToken != null) {
      await _pairViaQr(baseUrl, clientId);
    } else {
      await _pairViaApproval(baseUrl, clientId);
    }
  }

  Future<void> _pairViaQr(String baseUrl, String clientId) async {
    _addLog('Mode: QR code pairing');
    _addLog('Token: ${widget.qrToken!.substring(0, 12)}...');

    final store = context.read<SecureStore>();
    await store.savePairing(
      token: widget.qrToken!,
      host: widget.host,
      port: widget.port,
      certSha256: widget.certSha256 ?? '',
    );
    _addLog('Saved pairing to secure storage');

    final api = context.read<ApiClient>();
    final configured = await api.configureFromStore();
    _addLog('API configured: $configured (baseUrl=${api.dio.options.baseUrl})');

    // Confirm the QR token with the server
    final dio = _createPairingDio(baseUrl);

    try {
      _addLog('Confirming QR token...');
      final resp = await dio.post(
        '/api/auth/pair/qr/confirm',
        data: {
          'token': widget.qrToken,
          'device_name': _deviceName,
          'client_id': clientId,
        },
      );
      _addLog('Confirm response: ${resp.statusCode} ${resp.data}');

      if (resp.statusCode == 200) {
        _addLog('Pairing successful!');
        setState(() => _status = 'Connected!');
        await Future.delayed(const Duration(milliseconds: 800));
        _navigateHome();
      } else {
        _addLog('ERROR: Pairing failed — ${resp.data}');
        setState(() => _status = 'Pairing failed');
      }
    } catch (e) {
      _addLog('ERROR: $e');
      setState(() => _status = 'Connection error');
    }
  }

  Future<void> _pairViaApproval(String baseUrl, String clientId) async {
    _addLog('Mode: approval-based pairing');
    _addLog('Device: $_deviceName');
    _addLog('Pairing code: $_pairingCode');
    _addLog('Client ID: ${clientId.substring(0, 8)}...');

    final dio = _createPairingDio(baseUrl);

    try {
      _addLog('Submitting pairing request...');
      final resp = await dio.post(
        '/api/auth/pair/request',
        data: {
          'device_name': _deviceName,
          'pairing_code': _pairingCode,
          'client_id': clientId,
        },
      );
      _addLog('Request response: ${resp.statusCode} ${resp.data}');

      if (resp.statusCode != 200) {
        _addLog('ERROR: Failed to submit request');
        setState(() => _status = 'Request failed');
        return;
      }

      final requestId = resp.data['request_id'] as String;
      _addLog('Request ID: $requestId');
      _addLog('Waiting for approval (check web dashboard)...');

      // Poll for approval
      for (int i = 0; i < 60; i++) {
        await Future.delayed(const Duration(seconds: 2));
        try {
          final statusResp = await dio.get(
            '/api/auth/pair/request/$requestId/status',
          );
          final status = statusResp.data;
          _addLog('Poll #${i + 1}: status=${status['status']}');

          if (status['status'] == 'approved' || status['approved'] == true) {
            _addLog('Approved! Saving pairing...');
            // Get a fresh QR token for the pairing
            final qrResp = await dio.get('/api/auth/pair/qr');
            final qrData = qrResp.data;

            final store = context.read<SecureStore>();
            await store.savePairing(
              token: qrData['token'] as String,
              host: widget.host,
              port: widget.port,
              certSha256: qrData['cert_sha256'] ?? '',
            );

            final api = context.read<ApiClient>();
            await api.configureFromStore();

            // Confirm the token
            await dio.post(
              '/api/auth/pair/qr/confirm',
              data: {'token': qrData['token'], 'device_name': _deviceName, 'client_id': clientId},
            );

            _addLog('Pairing successful!');
            setState(() => _status = 'Connected!');
            await Future.delayed(const Duration(milliseconds: 800));
            _navigateHome();
            return;
          }

          if (status['status'] == 'denied') {
            _addLog('ERROR: Pairing denied');
            setState(() => _status = 'Pairing denied');
            return;
          }
        } catch (e) {
          _addLog('Poll error: $e');
        }
      }

      _addLog('ERROR: Approval timed out');
      setState(() => _status = 'Timed out');
    } catch (e) {
      _addLog('ERROR: $e');
      setState(() => _status = 'Connection error');
    }
  }

  void _navigateHome() {
    setState(() => _done = true);
    if (mounted) {
      Navigator.pushNamedAndRemoveUntil(context, '/', (_) => false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.connectingTitle)),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Text(
                  '${widget.host}:${widget.port}',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 4),
                Text(
                  _status,
                  style: TextStyle(
                    fontSize: 14,
                    color: _done ? Colors.green : Colors.orange,
                  ),
                ),
                if (widget.qrToken == null) ...[
                  const SizedBox(height: 12),
                  Text(l10n.pairingCodeLabel,
                      style: const TextStyle(fontSize: 11, color: Colors.grey)),
                  const SizedBox(height: 4),
                  Text(
                    _pairingCode,
                    style: const TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      fontFamily: 'monospace',
                      letterSpacing: 6,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(l10n.verifyCodeHint,
                      style: const TextStyle(fontSize: 11, color: Colors.grey)),
                ],
              ],
            ),
          ),
          const Divider(),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: _log.length,
              itemBuilder: (context, index) {
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Text(
                    _log[index],
                    style: const TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: Colors.grey,
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
