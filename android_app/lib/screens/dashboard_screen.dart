import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import '../app_theme.dart';
import '../providers/session_provider.dart';
import '../models/session.dart';
import '../services/notification_service.dart';
import '../services/secure_store.dart';
import '../services/api_client.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      // Request notification permission
      NotificationService.requestPermission();
      // Load notification prefs from storage
      final store = context.read<SecureStore>();
      final sound = await store.getNotifySound();
      final vibrate = await store.getNotifyVibrate();
      if (!mounted) return;
      NotificationService.updateSettings(sound: sound, vibrate: vibrate);
      // Connect SSE
      context.read<SessionProvider>().connectSse();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      context.read<SessionProvider>().loadSessions();
    }
  }

  @override
  Widget build(BuildContext context) {
    final store = context.read<SecureStore>();
    final l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.appTitle),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.pushNamed(context, '/settings'),
          ),
        ],
      ),
      drawer: _ServerDrawer(store: store),
      body: Consumer<SessionProvider>(
        builder: (context, provider, _) {
          if (provider.loading) {
            return const Center(child: CircularProgressIndicator());
          }
          final body = DefaultTabController(
            length: 3,
            child: Column(
              children: [
                TabBar(
                  tabs: [
                    Tab(text: l10n.activeTab(provider.active.length)),
                    Tab(text: l10n.completeTab(provider.complete.length)),
                    Tab(text: l10n.archivedTab(provider.archived.length)),
                  ],
                ),
                Expanded(
                  child: TabBarView(
                    children: [
                      _SessionList(
                        sessions: provider.active,
                        onArchive: provider.archiveSession,
                        onComplete: provider.markComplete,
                      ),
                      _SessionList(
                        sessions: provider.complete,
                        onArchive: provider.archiveSession,
                      ),
                      _SessionList(
                        sessions: provider.archived,
                        onUnarchive: provider.unarchiveSession,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );

          return Column(
            children: [
              if (!provider.connected)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  color: Colors.red.shade900,
                  child: Row(
                    children: [
                      const Icon(Icons.cloud_off, color: Colors.white70, size: 16),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          l10n.disconnectedBanner,
                          style: const TextStyle(color: Colors.white70, fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                ),
              _StateBar(provider: provider),
              Expanded(child: body),
            ],
          );
        },
      ),
    );
  }
}

class _SessionList extends StatelessWidget {
  final List<Session> sessions;
  final Function(String)? onArchive;
  final Function(String)? onUnarchive;
  final Function(String)? onComplete;

  const _SessionList({
    required this.sessions,
    this.onArchive,
    this.onUnarchive,
    this.onComplete,
  });

  @override
  Widget build(BuildContext context) {
    if (sessions.isEmpty) {
      final l10n = AppLocalizations.of(context)!;
      return Center(child: Text(l10n.noSessions));
    }
    return RefreshIndicator(
      onRefresh: () => context.read<SessionProvider>().loadSessions(),
      child: ListView.builder(
        itemCount: sessions.length,
        itemBuilder: (context, index) => _SessionCard(
          session: sessions[index],
          onArchive: onArchive,
          onUnarchive: onUnarchive,
          onComplete: onComplete,
          onTap: () => Navigator.pushNamed(
            context,
            '/session',
            arguments: sessions[index].sessionId,
          ),
        ),
      ),
    );
  }
}

class _SessionCard extends StatelessWidget {
  final Session session;
  final Function(String)? onArchive;
  final Function(String)? onUnarchive;
  final Function(String)? onComplete;
  final VoidCallback onTap;

  const _SessionCard({
    required this.session,
    this.onArchive,
    this.onUnarchive,
    this.onComplete,
    required this.onTap,
  });

  Color _stateColor() => AppTheme.stateColor(session.state);

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Dismissible(
      key: Key(session.sessionId),
      background: Container(
        color: Colors.orange,
        alignment: Alignment.centerLeft,
        padding: const EdgeInsets.only(left: 16),
        child: const Icon(Icons.archive, color: Colors.white),
      ),
      secondaryBackground: Container(
        color: Colors.green,
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 16),
        child: const Icon(Icons.check, color: Colors.white),
      ),
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          onArchive?.call(session.sessionId);
        } else {
          onComplete?.call(session.sessionId);
        }
        return false;
      },
      child: Card(
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        child: ListTile(
          onTap: onTap,
          leading: CircleAvatar(backgroundColor: _stateColor(), radius: 6),
          title: Text(session.summary ?? session.cwd, maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text([
            _stateLabel(session.state, l10n),
            if (session.ccMonitorUid.isNotEmpty) session.ccMonitorUid,
          ].join(' · ')),
          trailing: Text(_formatTime(session.updatedAt, l10n), style: Theme.of(context).textTheme.bodySmall),
        ),
      ),
    );
  }

  String _stateLabel(String state, AppLocalizations l10n) {
    return switch (state) {
      'working' => l10n.stateWorking,
      'idle' => l10n.stateIdle,
      'pending_approval' => l10n.statePendingApproval,
      'pending_review' => l10n.statePendingReview,
      'all_done' => l10n.stateAllDone,
      _ => l10n.stateArchived,
    };
  }

  String _formatTime(DateTime dt, AppLocalizations l10n) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 1) return l10n.timeJustNow;
    if (diff.inMinutes < 60) return l10n.timeMinutesAgo(diff.inMinutes);
    if (diff.inHours < 24) return l10n.timeHoursAgo(diff.inHours);
    return l10n.timeDaysAgo(diff.inDays);
  }
}

class _ServerDrawer extends StatefulWidget {
  final SecureStore store;
  const _ServerDrawer({required this.store});

  @override
  State<_ServerDrawer> createState() => _ServerDrawerState();
}

class _ServerDrawerState extends State<_ServerDrawer> {
  List<ServerEntry> _servers = [];
  ServerEntry? _active;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final servers = await widget.store.getServers();
    final active = await widget.store.getActive();
    setState(() { _servers = servers; _active = active; });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Drawer(
      child: Column(
        children: [
          DrawerHeader(
            decoration: const BoxDecoration(color: Colors.indigo),
            child: SizedBox(
              width: double.infinity,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  const Icon(Icons.dns, color: Colors.white70, size: 32),
                  const SizedBox(height: 8),
                  Text(l10n.servers, style: const TextStyle(color: Colors.white, fontSize: 18)),
                ],
              ),
            ),
          ),
          Expanded(
            child: _servers.isEmpty
                ? Center(child: Text(l10n.noServersPaired, style: const TextStyle(color: Colors.grey)))
                : ListView.builder(
                    itemCount: _servers.length,
                    itemBuilder: (context, index) {
                      final s = _servers[index];
                      final isActive = _active != null && s.host == _active!.host && s.port == _active!.port;
                      final connected = context.read<SessionProvider>().connected;
                      return ListTile(
                        leading: Icon(
                          isActive
                              ? (connected ? Icons.check_circle : Icons.warning_amber_rounded)
                              : Icons.circle_outlined,
                          color: isActive ? (connected ? Colors.green : Colors.orange) : Colors.grey,
                        ),
                        title: Text('${s.host}:${s.port}',
                            style: TextStyle(fontWeight: isActive ? FontWeight.bold : FontWeight.normal)),
                        subtitle: Text(s.displayId, style: const TextStyle(fontSize: 12, fontFamily: 'monospace')),
                        trailing: IconButton(
                          icon: const Icon(Icons.delete_outline, size: 18),
                          onPressed: () async {
                            await widget.store.removeServer(s.host, s.port);
                            _load();
                          },
                        ),
                        onTap: () async {
                          await widget.store.setActive(s.host, s.port);
                          final api = context.read<ApiClient>();
                          await api.configureFromStore();
                          context.read<SessionProvider>().loadSessions();
                          Navigator.pop(context);
                        },
                      );
                    },
                  ),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.add),
            title: Text(l10n.addServer),
            onTap: () {
              Navigator.pop(context);
              Navigator.pushNamed(context, '/servers');
            },
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

// ---- SSE state bar ----

class _StateBar extends StatelessWidget {
  final SessionProvider provider;
  const _StateBar({required this.provider});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final log = provider.eventLog;
    final lastEvent = log.firstOrNull;

    return GestureDetector(
      onTap: () {
        showModalBottomSheet(
          context: context,
          builder: (_) => _StateLogSheet(provider: provider),
        );
      },
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        color: provider.connected ? Colors.green.shade900 : Colors.red.shade900,
        child: Row(
          children: [
            Icon(
              provider.connected ? Icons.cloud_done : Icons.cloud_off,
              color: Colors.white70,
              size: 14,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                provider.connected
                    ? l10n.sseAlive(log.length)
                    : l10n.sseDisconnected,
                style: const TextStyle(color: Colors.white70, fontSize: 11),
              ),
            ),
            if (lastEvent != null)
              Text(
                '${lastEvent.time.hour.toString().padLeft(2, '0')}:${lastEvent.time.minute.toString().padLeft(2, '0')}:${lastEvent.time.second.toString().padLeft(2, '0')}',
                style: const TextStyle(color: Colors.white54, fontSize: 10),
              ),
          ],
        ),
      ),
    );
  }
}

class _StateLogSheet extends StatefulWidget {
  final SessionProvider provider;
  const _StateLogSheet({required this.provider});

  @override
  State<_StateLogSheet> createState() => _StateLogSheetState();
}

class _StateLogSheetState extends State<_StateLogSheet> {
  late LogLevel _level;

  @override
  void initState() {
    super.initState();
    _level = widget.provider.logLevel;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final allLog = widget.provider.eventLog;
    final log = widget.provider.filteredEventLog;
    return Container(
      height: MediaQuery.of(context).size.height * 0.6,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(l10n.eventLogTitle(log.length, allLog.length),
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              Text(widget.provider.connected ? l10n.eventLogConnected : l10n.eventLogDisconnected,
                  style: TextStyle(
                      color: widget.provider.connected ? Colors.green : Colors.red,
                      fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Text(l10n.eventLogLevel, style: const TextStyle(fontSize: 12)),
              DropdownButton<LogLevel>(
                value: _level,
                isDense: true,
                underline: const SizedBox(),
                items: LogLevel.values.map((l) {
                  return DropdownMenuItem(value: l, child: Text(l.label, style: const TextStyle(fontSize: 12)));
                }).toList(),
                onChanged: (val) {
                  if (val == null) return;
                  setState(() => _level = val);
                  widget.provider.setLogLevel(val);
                },
              ),
            ],
          ),
          const Divider(),
          Expanded(
            child: log.isEmpty
                ? Center(child: Text(l10n.eventLogEmpty))
                : ListView.builder(
                    itemCount: log.length,
                    itemBuilder: (_, i) {
                      final e = log[i];
                      return Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Row(
                          children: [
                            Text(
                              '${e.time.hour.toString().padLeft(2, '0')}:${e.time.minute.toString().padLeft(2, '0')}:${e.time.second.toString().padLeft(2, '0')}',
                              style: const TextStyle(
                                  fontSize: 11, fontFamily: 'monospace', color: Colors.grey),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                              decoration: BoxDecoration(
                                color: _badgeColor(e),
                                borderRadius: BorderRadius.circular(3),
                              ),
                              child: Text(e.type,
                                  style: const TextStyle(
                                      fontSize: 10,
                                      fontFamily: 'monospace',
                                      color: Colors.white70)),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(e.detail,
                                  style: const TextStyle(fontSize: 11),
                                  overflow: TextOverflow.ellipsis),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Color _badgeColor(SseEventEntry e) {
    return switch (e.level) {
      LogLevel.debug => Colors.grey.shade800,
      LogLevel.warning => Colors.orange.shade900,
      LogLevel.error => Colors.red.shade900,
      LogLevel.info => e.type == 'device_update' || e.type == 'ACTION'
          ? Colors.orange.shade900
          : Colors.blue.shade900,
    };
  }
}
