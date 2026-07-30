import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:cc_monitor_app/l10n/app_localizations.dart';
import '../services/notification_service.dart';
import '../providers/session_provider.dart';
import '../services/secure_store.dart';
import '../services/api_client.dart';

class SettingsScreen extends StatefulWidget {
  final ValueChanged<String?>? onLocaleChanged;

  const SettingsScreen({super.key, this.onLocaleChanged});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _sound = true;
  bool _vibrate = true;
  List<ServerEntry> _servers = [];
  ServerEntry? _active;
  String? _localeOverride;
  bool _serversLoaded = false;

  @override
  void initState() {
    super.initState();
    _sound = NotificationService.soundEnabled;
    _vibrate = NotificationService.vibrateEnabled;
    _loadServers();
    _loadLocale();
  }

  Future<void> _loadServers() async {
    final store = context.read<SecureStore>();
    final servers = await store.getServers();
    final active = await store.getActive();
    if (!mounted) return;
    setState(() {
      _servers = servers;
      _active = active;
      _serversLoaded = true;
    });
  }

  Future<void> _loadLocale() async {
    final store = context.read<SecureStore>();
    final loc = await store.getLocale();
    if (!mounted) return;
    setState(() => _localeOverride = loc);
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

  Future<void> _removeServer(String host, int port) async {
    final store = context.read<SecureStore>();
    await store.removeServer(host, port);
    // If no servers left, navigate to server picker
    final servers = await store.getServers();
    if (servers.isEmpty) {
      if (mounted) {
        Navigator.pushNamedAndRemoveUntil(context, '/servers', (_) => false);
      }
      return;
    }
    // If we removed the active server, switch to first available
    final active = await store.getActive();
    if (active == null) {
      await store.setActive(servers.first.host, servers.first.port);
    }
    await _loadServers();
    // Reload API config
    final api = context.read<ApiClient>();
    await api.configureFromStore();
    if (mounted) {
      context.read<SessionProvider>().connectSse();
      context.read<SessionProvider>().loadSessions();
    }
  }

  Future<void> _setLocale(String? locale) async {
    final store = context.read<SecureStore>();
    await store.setLocale(locale);
    setState(() => _localeOverride = locale);
    widget.onLocaleChanged?.call(locale);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final api = context.read<ApiClient>();
    final isActive = (ServerEntry s) =>
        _active != null && s.host == _active!.host && s.port == _active!.port;

    return Scaffold(
      appBar: AppBar(title: Text(l10n.settingsTitle)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          // ---- Servers section ----
          _sectionHeader(l10n.settingsServers),
          const SizedBox(height: 8),
          if (_servers.isEmpty && _serversLoaded)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Center(child: Text(l10n.noServersPaired)),
              ),
            )
          else
            ..._servers.map((s) => _serverCard(s, isActive(s), l10n)),

          const SizedBox(height: 4),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              icon: const Icon(Icons.add, size: 18),
              label: Text(l10n.settingsPairNew),
              onPressed: () => Navigator.pushNamed(context, '/servers'),
            ),
          ),

          const SizedBox(height: 24),

          // ---- Language section ----
          _sectionHeader(l10n.settingsLanguage),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<String?>(
                  value: _localeOverride,
                  isExpanded: true,
                  items: [
                    DropdownMenuItem(
                      value: null,
                      child: Text(l10n.settingsLanguageSystem),
                    ),
                    const DropdownMenuItem(
                      value: 'en',
                      child: Text('English'),
                    ),
                    const DropdownMenuItem(
                      value: 'zh',
                      child: Text('中文'),
                    ),
                  ],
                  onChanged: _setLocale,
                ),
              ),
            ),
          ),

          const SizedBox(height: 24),

          // ---- Notifications section ----
          _sectionHeader(l10n.settingsNotifications),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                SwitchListTile(
                  title: Text(l10n.settingsSound),
                  subtitle: Text(l10n.settingsSoundDesc),
                  value: _sound,
                  onChanged: _toggleSound,
                ),
                const Divider(height: 1),
                SwitchListTile(
                  title: Text(l10n.settingsVibration),
                  subtitle: Text(l10n.settingsVibrationDesc),
                  value: _vibrate,
                  onChanged: _toggleVibrate,
                ),
              ],
            ),
          ),

          const SizedBox(height: 24),

          // ---- About section ----
          _sectionHeader(l10n.settingsAbout),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.info_outline),
              title: Text(l10n.settingsAbout),
              subtitle: const Text('v0.4.1'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 4),
      child: Text(
        title.toUpperCase(),
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: Theme.of(context).colorScheme.primary,
          letterSpacing: 0.8,
        ),
      ),
    );
  }

  Widget _serverCard(ServerEntry s, bool active, AppLocalizations l10n) {
    final connected = context.watch<SessionProvider>().connected;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: active
            ? BorderSide(
                color: connected ? Colors.green : Colors.orange, width: 1.5)
            : BorderSide(
                color: Theme.of(context).dividerColor, width: 0.5),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
        child: Row(
          children: [
            // Status dot
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: active
                    ? (connected ? Colors.green : Colors.orange)
                    : Colors.grey.shade500,
              ),
            ),
            const SizedBox(width: 12),
            // Server info
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${s.host}:${s.port}',
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    [
                      s.displayId,
                      if (active) l10n.settingsActive,
                      if (!active) l10n.settingsInactive,
                    ].join(' · '),
                    style: TextStyle(
                      fontSize: 12,
                      color: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.color,
                    ),
                  ),
                ],
              ),
            ),
            // Forget button
            TextButton(
              onPressed: () => _removeServer(s.host, s.port),
              child: Text(
                l10n.settingsDelete,
                style: const TextStyle(color: Colors.red, fontSize: 13),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
