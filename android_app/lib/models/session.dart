class Session {
  final String sessionId;
  final String cwd;
  final String state;
  final String rawEvent;
  final String? rawDetail;
  final String? summary;
  final bool archived;
  final String ccMonitorUid;
  final DateTime updatedAt;

  const Session({
    required this.sessionId,
    required this.cwd,
    required this.state,
    required this.rawEvent,
    this.rawDetail,
    this.summary,
    this.archived = false,
    this.ccMonitorUid = '',
    required this.updatedAt,
  });

  factory Session.fromJson(Map<String, dynamic> json) {
    return Session(
      sessionId: json['session_id'] as String,
      cwd: json['cwd'] as String? ?? '',
      state: json['state'] as String,
      rawEvent: json['raw_event'] as String? ?? '',
      rawDetail: json['raw_detail'] as String?,
      summary: json['summary'] as String?,
      archived: json['archived'] as bool? ?? false,
      ccMonitorUid: json['cc_monitor_uid'] as String? ?? '',
      updatedAt: DateTime.parse(json['updated_at'] as String),
    );
  }

  bool get isActive => !archived && state != 'all_done';
  bool get isComplete => !archived && state == 'all_done';
}
