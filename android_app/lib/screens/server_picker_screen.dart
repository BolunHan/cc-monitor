import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/api_client.dart';
import '../services/discovery_service.dart';
import '../services/pairing_service.dart';
import '../services/secure_store.dart';

class ServerPickerScreen extends StatefulWidget {
  const ServerPickerScreen({super.key});

  @override
  State<ServerPickerScreen> createState() => _ServerPickerScreenState();
}

class _ServerPickerScreenState extends State<ServerPickerScreen> {
  final DiscoveryService _discovery = DiscoveryService();
  List<DiscoveredServer> _servers = [];
  bool _scanning = true;

  @override
  void initState() {
    super.initState();
    _scan();
  }

  Future<void> _scan() async {
    debugPrint('[cc-monitor:picker] Starting LAN scan...');
    setState(() => _scanning = true);
    try {
      _servers = await _discovery.discover();
      debugPrint('[cc-monitor:picker] Scan done: ${_servers.length} servers');
    } catch (e) {
      debugPrint('[cc-monitor:picker] Scan error: $e');
      _servers = [];
    }
    setState(() => _scanning = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Connect to Server')),
      body: Column(
        children: [
          if (_scanning)
            const LinearProgressIndicator(),
          Expanded(
            child: _scanning
                ? const Center(child: CircularProgressIndicator())
                : _servers.isEmpty
                    ? _buildEmpty()
                    : ListView.builder(
                        itemCount: _servers.length,
                        itemBuilder: (context, index) {
                          final s = _servers[index];
                          return ListTile(
                            leading: const Icon(Icons.computer),
                            title: Text(s.hostname),
                            subtitle: Text('${s.host}:${s.port}  ·  v${s.version}'),
                            trailing: const Icon(Icons.chevron_right),
                            onTap: () => _pairWithServer(s.host, s.port),
                          );
                        },
                      ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      icon: const Icon(Icons.qr_code_scanner),
                      label: const Text('Scan QR Code'),
                      onPressed: () => Navigator.pushNamed(context, '/pair'),
                    ),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.edit),
                      label: const Text('Manual Entry'),
                      onPressed: () => _showManualEntry(),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmpty() {
    return ListView(
      padding: const EdgeInsets.all(32),
      children: [
        const Icon(Icons.search_off, size: 64, color: Colors.grey),
        const SizedBox(height: 16),
        const Text(
          'No cc-monitor servers found on LAN',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 16),
        ),
        const SizedBox(height: 16),
        ElevatedButton.icon(
          onPressed: _scan,
          icon: const Icon(Icons.refresh),
          label: const Text('Scan Again'),
        ),
      ],
    );
  }

  void _pairWithServer(String host, int port) async {
    // Navigate to QR/approval flow with this server selected
    final pairingService = context.read<PairingService>();
    // Submit pairing request for approval
    final requestId = await pairingService.submitPairingRequest(
      host: host,
      port: port,
      deviceName: 'Android',
    );
    if (requestId != null && mounted) {
      _pollApproval(host, port, requestId);
    }
  }

  void _pollApproval(String host, int port, String requestId) async {
    final pairingService = context.read<PairingService>();
    while (mounted) {
      await Future.delayed(const Duration(seconds: 2));
      final status = await pairingService.pollRequestStatus(
        host: host, port: port, requestId: requestId,
      );
      if (status?['status'] == 'approved' || status?['approved'] == true) {
        if (mounted) {
          Navigator.pushNamedAndRemoveUntil(context, '/', (_) => false);
        }
        return;
      }
      if (status?['status'] == 'denied') {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Pairing denied')),
          );
        }
        return;
      }
    }
  }

  void _showManualEntry() {
    final hostController = TextEditingController();
    final portController = TextEditingController(text: '9876');
    final tokenController = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Manual Entry'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: hostController,
              decoration: const InputDecoration(labelText: 'Server IP'),
            ),
            TextField(
              controller: portController,
              decoration: const InputDecoration(labelText: 'Port'),
              keyboardType: TextInputType.number,
            ),
            TextField(
              controller: tokenController,
              decoration: const InputDecoration(labelText: 'Token'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final host = hostController.text.trim();
              final port = int.tryParse(portController.text.trim()) ?? 9876;
              final token = tokenController.text.trim();

              await context.read<SecureStore>().savePairing(
                    token: token,
                    host: host,
                    port: port,
                    certSha256: '', // user accepts cert on first connection
                  );

              if (context.mounted) {
                final api = context.read<ApiClient>();
                await api.configureFromStore();
                if (context.mounted) {
                  Navigator.pushNamedAndRemoveUntil(
                      ctx, '/', (_) => false);
                }
              }
            },
            child: const Text('Connect'),
          ),
        ],
      ),
    );
  }
}
