import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:provider/provider.dart';
import 'dart:convert';
import '../services/secure_store.dart';
import '../services/api_client.dart';

class PairingScreen extends StatefulWidget {
  const PairingScreen({super.key});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  MobileScannerController? _controller;
  bool _paired = false;

  @override
  void initState() {
    super.initState();
    _controller = MobileScannerController();
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    if (_paired) return;
    final barcode = capture.barcodes.firstOrNull;
    if (barcode?.rawValue == null) return;

    try {
      final data = jsonDecode(barcode!.rawValue!) as Map<String, dynamic>;
      _handleQrData(data);
    } catch (_) {}
  }

  Future<void> _handleQrData(Map<String, dynamic> data) async {
    final token = data['token'] as String?;
    final host = data['host'] as String?;
    final port = data['port'] as int?;
    final certSha256 = data['cert_sha256'] as String?;

    if (token == null || host == null || port == null) return;

    setState(() => _paired = true);

    final store = context.read<SecureStore>();
    await store.savePairing(
      token: token,
      host: host,
      port: port,
      certSha256: certSha256 ?? '',
    );

    final api = context.read<ApiClient>();
    await api.configureFromStore();

    // Confirm the QR token
    final dio = api.dio;
    await dio.post(
      '/api/auth/pair/qr/confirm',
      data: {'token': token, 'device_name': 'Android'},
    );

    if (mounted) {
      Navigator.pushNamedAndRemoveUntil(context, '/', (_) => false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan QR Code')),
      body: MobileScanner(
        controller: _controller,
        onDetect: _onDetect,
      ),
    );
  }
}
