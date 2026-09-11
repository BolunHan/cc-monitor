/// One labelled block of a pending request's content.
///
/// Built server-side and tool-aware, so the client renders it without knowing
/// what a `Write` or a plan is — which is what keeps this screen and the web
/// dashboard showing the same thing.
class RequestDetail {
  final String label;
  final String value;

  /// `code`, `text` or `diff`. Only affects presentation.
  final String kind;
  final bool truncated;

  const RequestDetail({
    required this.label,
    required this.value,
    this.kind = 'code',
    this.truncated = false,
  });

  factory RequestDetail.fromJson(Map<String, dynamic> json) => RequestDetail(
        label: json['label'] as String? ?? '',
        value: json['value'] as String? ?? '',
        kind: json['kind'] as String? ?? 'code',
        truncated: json['truncated'] as bool? ?? false,
      );
}

class QuestionOption {
  final String label;
  final String description;

  const QuestionOption({required this.label, this.description = ''});

  factory QuestionOption.fromJson(Map<String, dynamic> json) => QuestionOption(
        label: json['label'] as String? ?? '',
        description: json['description'] as String? ?? '',
      );
}

/// One question of an `AskUserQuestion` call.
///
/// Grouped per question, not flattened: Claude Code wants an answer for
/// *every* question in a call, so the UI has to know how many there are before
/// it can submit.
class RequestQuestion {
  final String question;
  final String header;
  final bool multiSelect;
  final List<QuestionOption> options;

  const RequestQuestion({
    required this.question,
    this.header = '',
    this.multiSelect = false,
    this.options = const [],
  });

  factory RequestQuestion.fromJson(Map<String, dynamic> json) => RequestQuestion(
        question: json['question'] as String? ?? '',
        header: json['header'] as String? ?? '',
        multiSelect: json['multi_select'] as bool? ?? false,
        options: (json['options'] as List? ?? [])
            .map((o) => QuestionOption.fromJson(o as Map<String, dynamic>))
            .toList(),
      );
}

/// A decision an agent is blocked on.
class PendingRequest {
  final String requestId;

  /// `permission`, `question` or `plan`.
  final String kind;
  final String? toolName;
  final String preview;
  final List<RequestDetail> details;
  final List<RequestQuestion> questions;
  final List<QuestionOption> options;

  /// False once the hook has let go of the terminal dialog — the request is
  /// being answered locally, so an answer from here can no longer reach it.
  final bool holding;

  const PendingRequest({
    required this.requestId,
    required this.kind,
    this.toolName,
    this.preview = '',
    this.details = const [],
    this.questions = const [],
    this.options = const [],
    this.holding = true,
  });

  bool get isQuestion => kind == 'question' && questions.isNotEmpty;

  /// A single single-select question can be answered with one tap. Anything
  /// else needs explicit selection, or the first tap would answer before the
  /// remaining questions were chosen.
  bool get isOneTap =>
      questions.length == 1 && !questions.first.multiSelect;

  factory PendingRequest.fromJson(Map<String, dynamic> json) => PendingRequest(
        requestId: json['request_id'] as String? ?? '',
        kind: json['kind'] as String? ?? 'permission',
        toolName: json['tool_name'] as String?,
        preview: json['preview'] as String? ?? '',
        holding: json['holding'] as bool? ?? true,
        details: (json['details'] as List? ?? [])
            .map((d) => RequestDetail.fromJson(d as Map<String, dynamic>))
            .toList(),
        questions: (json['questions'] as List? ?? [])
            .map((q) => RequestQuestion.fromJson(q as Map<String, dynamic>))
            .toList(),
        options: (json['options'] as List? ?? [])
            .map((o) => QuestionOption.fromJson(o as Map<String, dynamic>))
            .toList(),
      );
}

/// A message a user pushed into a session, delivered at the next turn boundary.
class QueuedDirective {
  final String directiveId;
  final String text;
  final bool delivered;

  const QueuedDirective({
    required this.directiveId,
    required this.text,
    this.delivered = false,
  });

  factory QueuedDirective.fromJson(Map<String, dynamic> json) => QueuedDirective(
        directiveId: json['directive_id'] as String? ?? '',
        text: json['text'] as String? ?? '',
        delivered: json['delivered_at'] != null,
      );
}

class Session {
  final String sessionId;
  final String cwd;
  final String state;
  final String rawEvent;
  final String? rawDetail;
  final String? summary;
  final bool archived;
  final String ccMonitorUid;
  final String agent;
  final DateTime updatedAt;

  /// The decision this session is blocked on, if any.
  final PendingRequest? pendingRequest;

  /// Set when a stop was requested from a UI and not yet cleared.
  final bool stopRequested;
  final String? stopReason;

  /// Directives typed into a UI but not yet handed to the agent.
  final List<QueuedDirective> queuedDirectives;

  const Session({
    required this.sessionId,
    required this.cwd,
    required this.state,
    required this.rawEvent,
    this.rawDetail,
    this.summary,
    this.archived = false,
    this.ccMonitorUid = '',
    this.agent = 'claude',
    required this.updatedAt,
    this.pendingRequest,
    this.stopRequested = false,
    this.stopReason,
    this.queuedDirectives = const [],
  });

  factory Session.fromJson(Map<String, dynamic> json) {
    final rawRequest = json['pending_request'];
    return Session(
      sessionId: json['session_id'] as String,
      cwd: json['cwd'] as String? ?? '',
      state: json['state'] as String,
      rawEvent: json['raw_event'] as String? ?? '',
      rawDetail: json['raw_detail'] as String?,
      summary: json['summary'] as String?,
      archived: json['archived'] as bool? ?? false,
      ccMonitorUid: json['cc_monitor_uid'] as String? ?? '',
      agent: json['agent'] as String? ?? 'claude',
      updatedAt: DateTime.parse(json['updated_at'] as String),
      pendingRequest: rawRequest is Map<String, dynamic>
          ? PendingRequest.fromJson(rawRequest)
          : null,
      stopRequested: json['stop_requested'] as bool? ?? false,
      stopReason: json['stop_reason'] as String?,
      queuedDirectives: (json['queued_directives'] as List? ?? [])
          .map((d) => QueuedDirective.fromJson(d as Map<String, dynamic>))
          .toList(),
    );
  }

  /// Directives typed but not yet delivered, so the UI can say how many are
  /// waiting rather than leaving the user wondering whether Send worked.
  int get undeliveredDirectiveCount =>
      queuedDirectives.where((d) => !d.delivered).length;

  bool get isActive => !archived && state != 'all_done';
  bool get isComplete => !archived && state == 'all_done';
}
