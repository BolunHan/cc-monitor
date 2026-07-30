import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import '../providers/pairing_provider.dart';
import '../services/notification_service.dart';
import '../services/secure_store.dart';
import '../services/pairing_service.dart';
import '../services/api_client.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _sound = true;
  bool _vibrate = true;

  @override
  void initState() {
    super.initState();
    _sound = NotificationService.soundEnabled;
    _vibrate = NotificationService.vibrateEnabled;
  }

  Future<void> _toggleSound(bool val) async {
    setState(() => _sound = val);
    NotificationService.updateSettings(sound: val, vibrate: _vibrate);
    await context.read<SecureStore>().setNotifySound(val);
  }

  Future<void> _toggleVibrate(bool val) async {
    setState(() => _vibrate = val);
    NotificationService.updateSettings(sound: _sound, vibrate: val);
    await context.read<SecureStore>().setNotifyVibrate(val);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.settingsTitle)),
      body: Consumer<PairingProvider>(
        builder: (context, pp, _) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              ListTile(
                leading: const Icon(Icons.dns),
                title: Text(l10n.settingsServer),
                subtitle: Text(context.read<ApiClient>().dio.options.baseUrl),
              ),
              ListTile(
                leading: const Icon(Icons.key),
                title: Text(l10n.settingsTokenStatus),
                subtitle: Text(pp.tokenExpiringSoon
                    ? l10n.settingsTokenExpires(pp.tokenExpiresAt)
                    : l10n.settingsTokenValid),
                trailing: pp.tokenExpiringSoon
                    ? ElevatedButton(
                        onPressed: () => context.read<PairingService>().rotateToken(),
                        child: Text(l10n.settingsRotate),
                      )
                    : null,
              ),
              const Divider(),
              ListTile(
                leading: const Icon(Icons.qr_code),
                title: Text(l10n.settingsPairNew),
                onTap: () => Navigator.pushNamed(context, '/servers'),
              ),
              ListTile(
                leading: const Icon(Icons.delete_forever, color: Colors.red),
                title: Text(l10n.settingsForget),
                subtitle: Text(l10n.settingsForgetDesc),
                onTap: () async {
                  await context.read<SecureStore>().clear();
                  if (context.mounted) {
                    Navigator.pushNamedAndRemoveUntil(
                        context, '/servers', (_) => false);
                  }
                },
              ),
              const Divider(),
              ListTile(
                leading: const Icon(Icons.notifications),
                title: Text(l10n.settingsNotifications),
              ),
              SwitchListTile(
                title: Text(l10n.settingsSound),
                subtitle: Text(l10n.settingsSoundDesc),
                value: _sound,
                onChanged: _toggleSound,
              ),
              SwitchListTile(
                title: Text(l10n.settingsVibration),
                subtitle: Text(l10n.settingsVibrationDesc),
                value: _vibrate,
                onChanged: _toggleVibrate,
              ),
              const Divider(),
              ListTile(
                leading: const Icon(Icons.info),
                title: Text(l10n.settingsAbout),
                subtitle: const Text('v0.4.1'),
              ),
            ],
          );
        },
      ),
    );
  }
}
