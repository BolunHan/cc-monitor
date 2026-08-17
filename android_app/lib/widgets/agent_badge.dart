import 'package:flutter/material.dart';

/// Colored [cc] / [dsh] badge shown left of a session title.
///
/// Claude Code sessions are claude-orange (#D97706) and DSH sessions are
/// DeepSeek blue (#4D6BFE). Older sessions without an `agent` field are
/// treated as Claude for backward compatibility.
class AgentBadge extends StatelessWidget {
  final String agent;

  const AgentBadge({super.key, this.agent = 'claude'});

  @override
  Widget build(BuildContext context) {
    final isDsh = agent == 'dsh';
    final color = isDsh
        ? const Color(0xFF4D6BFE)
        : const Color(0xFFD97706);
    final label = isDsh ? '[dsh]' : '[cc]';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withAlpha(28),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withAlpha(90), width: 0.8),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: color,
          letterSpacing: 0.03,
        ),
      ),
    );
  }
}
