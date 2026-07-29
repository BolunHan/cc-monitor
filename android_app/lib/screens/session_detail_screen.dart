import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/session_provider.dart';

class SessionDetailScreen extends StatelessWidget {
  final String sessionId;

  const SessionDetailScreen({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context) {
    return Consumer<SessionProvider>(
      builder: (context, provider, _) {
        final session = [...provider.active, ...provider.complete, ...provider.archived]
            .where((s) => s.sessionId == sessionId)
            .firstOrNull;

        if (session == null) {
          return Scaffold(
            appBar: AppBar(title: const Text('Session')),
            body: const Center(child: Text('Session not found')),
          );
        }

        return Scaffold(
          appBar: AppBar(title: Text(session.summary ?? sessionId)),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _InfoRow('Session ID', session.sessionId),
              if (session.ccMonitorUid.isNotEmpty)
                _InfoRow('UID', session.ccMonitorUid),
              _InfoRow('State', session.state),
              _InfoRow('CWD', session.cwd),
              _InfoRow('Last Event', session.rawEvent),
              if (session.rawDetail != null)
                _InfoRow('Detail', session.rawDetail!),
              _InfoRow('Updated', session.updatedAt.toString()),
              const SizedBox(height: 24),
              if (!session.archived)
                ElevatedButton.icon(
                  onPressed: () => provider.archiveSession(session.sessionId),
                  icon: const Icon(Icons.archive),
                  label: const Text('Archive'),
                ),
              if (session.archived)
                ElevatedButton.icon(
                  onPressed: () => provider.unarchiveSession(session.sessionId),
                  icon: const Icon(Icons.unarchive),
                  label: const Text('Unarchive'),
                ),
              const SizedBox(height: 8),
              if (session.state != 'all_done')
                ElevatedButton.icon(
                  onPressed: () => provider.markComplete(session.sessionId),
                  icon: const Icon(Icons.check),
                  label: const Text('Mark Complete'),
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label, value;
  const _InfoRow(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(label, style: const TextStyle(fontWeight: FontWeight.w500)),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
