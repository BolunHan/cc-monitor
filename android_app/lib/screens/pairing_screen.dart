import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'dart:convert';
import 'connecting_screen.dart';

class PairingScreen extends StatefulWidget {
  const PairingScreen({super.key});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  MobileScannerController? _controller;
  bool _navigating = false;

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
    if (_navigating) return;
    final barcode = capture.barcodes.firstOrNull;
    if (barcode?.rawValue == null) return;

    try {
      final data = jsonDecode(barcode!.rawValue!) as Map<String, dynamic>;
      final token = data['token'] as String?;
      final host = data['host'] as String?;
      final port = data['port'] as int?;
      final certSha256 = data['cert_sha256'] as String?;

      if (token == null || host == null || port == null) {
        debugPrint('[cc-monitor:qr] Incomplete QR data: $data');
        return;
      }

      debugPrint('[cc-monitor:qr] QR scanned: $host:$port token=${token.substring(0, 12)}...');
      setState(() => _navigating = true);
      _controller?.stop();

      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ConnectingScreen(
            host: host,
            port: port,
            qrToken: token,
            certSha256: certSha256,
          ),
        ),
      );
    } catch (e) {
      debugPrint('[cc-monitor:qr] Scan error: $e');
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
