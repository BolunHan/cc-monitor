import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:cc_monitor_app/l10n/app_localizations.dart';
import 'connecting_screen.dart';

class PairingScreen extends StatefulWidget {
  const PairingScreen({super.key});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  MobileScannerController? _controller;
  bool _navigating = false;
  String _lastScan = '';

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

  Map<String, dynamic>? _parsePayload(String raw) {
    // Try JSON first
    try {
      return jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {}

    // Try URL scheme: ccmonitor://pair?t=<token>&h=<host>&p=<port>&c=<cert>
    try {
      final uri = Uri.parse(raw);
      if (uri.scheme == 'ccmonitor' && uri.host == 'pair') {
        return {
          'token': uri.queryParameters['t'],
          'host': uri.queryParameters['h'],
          'port': int.tryParse(uri.queryParameters['p'] ?? ''),
          'cert_sha256': uri.queryParameters['c'],
        };
      }
    } catch (_) {}

    return null;
  }

  void _onDetect(BarcodeCapture capture) {
    if (_navigating) return;
    final barcode = capture.barcodes.firstOrNull;
    if (barcode?.rawValue == null) return;

    final raw = barcode!.rawValue!;
    if (raw == _lastScan) return; // ignore duplicate scans
    _lastScan = raw;

    debugPrint('[cc-monitor:qr] Scanned: ${raw.substring(0, raw.length.clamp(0, 80))}');

    final data = _parsePayload(raw);
    if (data == null) {
      setState(() => _lastScan = 'Invalid: $raw');
      return;
    }

    final token = data['token'] as String?;
    final host = data['host'] as String?;
    final port = data['port'] as int?;
    final certSha256 = data['cert_sha256'] as String?;

    if (token == null || host == null || port == null) {
      setState(() => _lastScan = 'Incomplete: $data');
      return;
    }

    debugPrint('[cc-monitor:qr] Valid: $host:$port token=${token.substring(0, 12)}...');
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
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.scanQrTitle)),
      body: Stack(
        children: [
          MobileScanner(
            controller: _controller,
            onDetect: _onDetect,
          ),
          // Scanning overlay
          Center(
            child: Container(
              width: 250,
              height: 250,
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white70, width: 2),
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
          // Status bar at bottom
          Positioned(
            bottom: 80,
            left: 16,
            right: 16,
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.black87,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                _navigating
                    ? l10n.scanFound
                    : _lastScan.isNotEmpty
                        ? _lastScan
                        : l10n.scanHint,
                style: const TextStyle(color: Colors.white70, fontSize: 13),
                textAlign: TextAlign.center,
              ),
            ),
          ),
          if (_navigating)
            Container(
              color: Colors.black54,
              child: const Center(child: CircularProgressIndicator()),
            ),
        ],
      ),
    );
  }
}
