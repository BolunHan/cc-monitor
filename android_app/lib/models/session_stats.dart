/// Aggregate statistics for a session.
class SessionStats {
  final int totalPrompts;
  final int totalAssistantMessages;
  final int totalToolCalls;
  final int totalInputTokens;
  final int totalOutputTokens;
  final Map<String, int> toolBreakdown;
  final String? sessionStart;
  final String? sessionEnd;
  final int durationSeconds;
  final int sizeBytes;

  const SessionStats({
    this.totalPrompts = 0,
    this.totalAssistantMessages = 0,
    this.totalToolCalls = 0,
    this.totalInputTokens = 0,
    this.totalOutputTokens = 0,
    this.toolBreakdown = const {},
    this.sessionStart,
    this.sessionEnd,
    this.durationSeconds = 0,
    this.sizeBytes = 0,
  });

  factory SessionStats.fromJson(Map<String, dynamic> json) {
    return SessionStats(
      totalPrompts: json['total_prompts'] as int? ?? 0,
      totalAssistantMessages: json['total_assistant_messages'] as int? ?? 0,
      totalToolCalls: json['total_tool_calls'] as int? ?? 0,
      totalInputTokens: json['total_input_tokens'] as int? ?? 0,
      totalOutputTokens: json['total_output_tokens'] as int? ?? 0,
      toolBreakdown: (json['tool_breakdown'] as Map<String, dynamic>?)
              ?.map((k, v) => MapEntry(k, (v as num).toInt())) ??
          {},
      sessionStart: json['session_start'] as String?,
      sessionEnd: json['session_end'] as String?,
      durationSeconds: json['duration_seconds'] as int? ?? 0,
      sizeBytes: json['size_bytes'] as int? ?? 0,
    );
  }

  String get formattedDuration {
    final d = durationSeconds;
    if (d >= 3600) {
      return '${d ~/ 3600}h ${(d % 3600) ~/ 60}m';
    }
    if (d >= 60) {
      return '${d ~/ 60}m ${d % 60}s';
    }
    return '${d}s';
  }

  String get formattedSize {
    final b = sizeBytes;
    if (b < 1024) return '$b B';
    if (b < 1048576) return '${(b / 1024).toStringAsFixed(1)} KB';
    return '${(b / 1048576).toStringAsFixed(1)} MB';
  }
}
