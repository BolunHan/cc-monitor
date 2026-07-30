import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:cc_monitor_app/l10n/app_localizations.dart';
import '../services/api_client.dart';
import '../services/discovery_service.dart';
import '../services/secure_store.dart';
import 'connecting_screen.dart';

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
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.connectTitle)),
      body: Column(
        children: [
          if (_scanning)
            const LinearProgressIndicator(),
          Expanded(
            child: _scanning
                ? const Center(child: CircularProgressIndicator())
                : _servers.isEmpty
                    ? _buildEmpty(l10n)
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
                      label: Text(l10n.connectScanQr),
                      onPressed: () => Navigator.pushNamed(context, '/pair'),
                    ),
                  ),
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      icon: const Icon(Icons.edit),
                      label: Text(l10n.connectManual),
                      onPressed: () => _showManualEntry(l10n),
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

  Widget _buildEmpty(AppLocalizations l10n) {
    return ListView(
      padding: const EdgeInsets.all(32),
      children: [
        const Icon(Icons.search_off, size: 64, color: Colors.grey),
        const SizedBox(height: 16),
        Text(
          l10n.connectNoServers,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 16),
        ),
        const SizedBox(height: 16),
        ElevatedButton.icon(
          onPressed: _scan,
          icon: const Icon(Icons.refresh),
          label: Text(l10n.connectScanAgain),
        ),
      ],
    );
  }

  void _pairWithServer(String host, int port) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ConnectingScreen(
          host: host,
          port: port,
        ),
      ),
    );
  }

  void _showManualEntry(AppLocalizations l10n) {
    final hostController = TextEditingController();
    final portController = TextEditingController(text: '9876');
    final tokenController = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.connectManualTitle),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: hostController,
              decoration: InputDecoration(labelText: l10n.connectServerIp),
            ),
            TextField(
              controller: portController,
              decoration: InputDecoration(labelText: l10n.connectPort),
              keyboardType: TextInputType.number,
            ),
            TextField(
              controller: tokenController,
              decoration: InputDecoration(labelText: l10n.connectToken),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(l10n.connectCancel),
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
            child: Text(l10n.connectConnect),
          ),
        ],
      ),
    );
  }
}
