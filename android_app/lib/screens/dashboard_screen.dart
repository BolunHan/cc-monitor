import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/session_provider.dart';
import '../models/session.dart';
import '../services/secure_store.dart';
import '../services/api_client.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<SessionProvider>().connectSse();
    });
  }

  @override
  Widget build(BuildContext context) {
    final store = context.read<SecureStore>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('cc-monitor'),
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
          return DefaultTabController(
            length: 3,
            child: Column(
              children: [
                TabBar(
                  tabs: [
                    Tab(text: 'Active (${provider.active.length})'),
                    Tab(text: 'Complete (${provider.complete.length})'),
                    Tab(text: 'Archived (${provider.archived.length})'),
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
      return const Center(child: Text('No sessions'));
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

  Color _stateColor() {
    return switch (session.state) {
      'working' => Colors.orange,
      'pending_review' => Colors.blue,
      'pending_approval' => Colors.red,
      'idle' => Colors.grey,
      'all_done' => Colors.green,
      _ => Colors.grey,
    };
  }

  @override
  Widget build(BuildContext context) {
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
          leading: CircleAvatar(
            backgroundColor: _stateColor(),
            radius: 6,
          ),
          title: Text(
            session.summary ?? session.cwd,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          subtitle: Text(session.state.replaceAll('_', ' ')),
          trailing: Text(
            _formatTime(session.updatedAt),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ),
      ),
    );
  }

  String _formatTime(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
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
    return Drawer(
      child: Column(
        children: [
          const DrawerHeader(
            decoration: BoxDecoration(color: Colors.indigo),
            child: SizedBox(
              width: double.infinity,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  Icon(Icons.dns, color: Colors.white70, size: 32),
                  SizedBox(height: 8),
                  Text('Servers', style: TextStyle(color: Colors.white, fontSize: 18)),
                ],
              ),
            ),
          ),
          Expanded(
            child: _servers.isEmpty
                ? const Center(child: Text('No servers paired', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    itemCount: _servers.length,
                    itemBuilder: (context, index) {
                      final s = _servers[index];
                      final isActive = _active != null &&
                          s.host == _active!.host && s.port == _active!.port;
                      return ListTile(
                        leading: Icon(
                          isActive ? Icons.check_circle : Icons.circle_outlined,
                          color: isActive ? Colors.green : Colors.grey,
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
            title: const Text('Add Server'),
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
