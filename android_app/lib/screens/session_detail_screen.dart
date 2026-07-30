import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_gen/gen_l10n/app_localizations.dart';
import '../providers/session_provider.dart';

class SessionDetailScreen extends StatelessWidget {
  final String sessionId;

  const SessionDetailScreen({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Consumer<SessionProvider>(
      builder: (context, provider, _) {
        final session = [...provider.active, ...provider.complete, ...provider.archived]
            .where((s) => s.sessionId == sessionId)
            .firstOrNull;

        if (session == null) {
          return Scaffold(
            appBar: AppBar(title: Text(l10n.sessionTitle)),
            body: Center(child: Text(l10n.sessionNotFound)),
          );
        }

        return Scaffold(
          appBar: AppBar(title: Text(session.summary ?? sessionId)),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _InfoRow(l10n.sessionId, session.sessionId),
              if (session.ccMonitorUid.isNotEmpty)
                _InfoRow(l10n.sessionUid, session.ccMonitorUid),
              _InfoRow(l10n.sessionState, session.state),
              _InfoRow(l10n.sessionCwd, session.cwd),
              _InfoRow(l10n.sessionLastEvent, session.rawEvent),
              if (session.rawDetail != null)
                _InfoRow(l10n.sessionDetail, session.rawDetail!),
              _InfoRow(l10n.sessionUpdated, session.updatedAt.toString()),
              const SizedBox(height: 24),
              if (!session.archived)
                ElevatedButton.icon(
                  onPressed: () => provider.archiveSession(session.sessionId),
                  icon: const Icon(Icons.archive),
                  label: Text(l10n.archive),
                ),
              if (session.archived)
                ElevatedButton.icon(
                  onPressed: () => provider.unarchiveSession(session.sessionId),
                  icon: const Icon(Icons.unarchive),
                  label: Text(l10n.unarchive),
                ),
              const SizedBox(height: 8),
              if (session.state != 'all_done')
                ElevatedButton.icon(
                  onPressed: () => provider.markComplete(session.sessionId),
                  icon: const Icon(Icons.check),
                  label: Text(l10n.markComplete),
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
