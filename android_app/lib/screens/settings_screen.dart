import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/pairing_provider.dart';
import '../services/secure_store.dart';
import '../services/pairing_service.dart';
import '../services/api_client.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: Consumer<PairingProvider>(
        builder: (context, pp, _) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              ListTile(
                leading: const Icon(Icons.dns),
                title: const Text('Server'),
                subtitle: Text(context.read<ApiClient>().dio.options.baseUrl),
              ),
              ListTile(
                leading: const Icon(Icons.key),
                title: const Text('Token Status'),
                subtitle: Text(pp.tokenExpiringSoon
                    ? 'Expires: ${pp.tokenExpiresAt}'
                    : 'Valid'),
                trailing: pp.tokenExpiringSoon
                    ? ElevatedButton(
                        onPressed: () => context.read<PairingService>().rotateToken(),
                        child: const Text('Rotate'),
                      )
                    : null,
              ),
              const Divider(),
              ListTile(
                leading: const Icon(Icons.qr_code),
                title: const Text('Pair New Server'),
                onTap: () => Navigator.pushNamed(context, '/servers'),
              ),
              ListTile(
                leading: const Icon(Icons.delete_forever, color: Colors.red),
                title: const Text('Forget Server'),
                subtitle: const Text('Clear all pairing data'),
                onTap: () async {
                  await context.read<SecureStore>().clear();
                  if (context.mounted) {
                    Navigator.pushNamedAndRemoveUntil(
                        context, '/servers', (_) => false);
                  }
                },
              ),
              const Divider(),
              const ListTile(
                leading: Icon(Icons.info),
                title: Text('cc-monitor App'),
                subtitle: Text('v0.4.1'),
              ),
            ],
          );
        },
      ),
    );
  }
}
