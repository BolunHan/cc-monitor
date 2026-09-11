import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/session.dart';
import '../providers/session_provider.dart';

/// Human-readable result of a control action.
///
/// "delivered" and "missed" are kept distinct on purpose: the second means the
/// prompt had already been answered at the terminal, so the user's tap did
/// nothing and telling them it worked would be a lie.
String controlOutcomeLabel(AppLocalizations l10n, ControlOutcome outcome) {
  return switch (outcome) {
    ControlOutcome.delivered => l10n.controlDelivered,
    ControlOutcome.missed => l10n.controlMissed,
    ControlOutcome.queued => l10n.controlQueuedOk,
    ControlOutcome.rejected => l10n.controlRejected,
    ControlOutcome.failed => l10n.controlFailed,
  };
}

/// The decision an agent is blocked on, with the content needed to review it.
///
/// Content comes from the server already structured (`details`, `questions`),
/// so this widget knows nothing about Claude Code's tools — it renders labelled
/// blocks and question groups, and the web dashboard renders the same payload
/// the same way.
class PendingRequestCard extends StatefulWidget {
  final PendingRequest request;

  /// Performs the answer. Kept out of this widget so it stays presentation-
  /// only and the parent owns the API call and its error reporting.
  final Future<void> Function(String behavior, Map<String, String>? answers)
      onRespond;

  /// True on the session list (tighter spacing), false on the detail screen.
  final bool dense;

  const PendingRequestCard({
    super.key,
    required this.request,
    required this.onRespond,
    this.dense = false,
  });

  @override
  State<PendingRequestCard> createState() => _PendingRequestCardState();
}

class _PendingRequestCardState extends State<PendingRequestCard> {
  /// qIndex → typed free-text answer. Overrides the option selection.
  final Map<int, TextEditingController> _custom = {};

  /// "qIndex:label" → selected. Multi-select questions keep several.
  final Set<String> _selected = {};

  bool _busy = false;

  @override
  void dispose() {
    for (final c in _custom.values) {
      c.dispose();
    }
    super.dispose();
  }

  TextEditingController _controllerFor(int index) =>
      _custom.putIfAbsent(index, TextEditingController.new);

  bool get _holding => widget.request.holding;

  /// Every question has an answer (typed or selected). Claude Code wants an
  /// answer for *each* question in a call, so submitting early would send a
  /// partial map.
  bool get _complete {
    final questions = widget.request.questions;
    for (var i = 0; i < questions.length; i++) {
      final typed = _custom[i]?.text.trim() ?? '';
      if (typed.isNotEmpty) continue;
      if (_selected.any((k) => k.startsWith('$i:'))) continue;
      return false;
    }
    return true;
  }

  Map<String, String> _collectAnswers() {
    final answers = <String, String>{};
    final questions = widget.request.questions;
    for (var i = 0; i < questions.length; i++) {
      final typed = _custom[i]?.text.trim() ?? '';
      if (typed.isNotEmpty) {
        answers[questions[i].question] = typed;
        continue;
      }
      final picked = _selected
          .where((k) => k.startsWith('$i:'))
          .map((k) => k.substring(k.indexOf(':') + 1))
          .toList();
      if (picked.isNotEmpty) answers[questions[i].question] = picked.join(', ');
    }
    return answers;
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _tapOption(int qIndex, QuestionOption option) {
    final questions = widget.request.questions;
    final multi = questions[qIndex].multiSelect;
    final key = '$qIndex:${option.label}';

    // A single single-select question is the common case; there the tap *is*
    // the answer. Anything else selects, and Submit sends — answering on the
    // first tap would pre-empt the remaining questions.
    if (widget.request.isOneTap) {
      _run(() => widget.onRespond('allow', {questions[qIndex].question: option.label}));
      return;
    }

    setState(() {
      // Typing takes precedence over picking, so clear it on an explicit pick.
      _custom[qIndex]?.clear();
      if (multi) {
        _selected.contains(key) ? _selected.remove(key) : _selected.add(key);
      } else {
        _selected.removeWhere((k) => k.startsWith('$qIndex:'));
        _selected.add(key);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final req = widget.request;
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final accent = _holding ? Colors.amber : theme.disabledColor;
    final pad = widget.dense ? 10.0 : 14.0;
    final toolName = req.toolName;

    return Container(
      width: double.infinity,
      margin: EdgeInsets.only(top: widget.dense ? 6 : 10, bottom: 4),
      padding: EdgeInsets.all(pad),
      decoration: BoxDecoration(
        color: accent.withAlpha(isDark ? 26 : 18),
        border: Border.all(color: accent.withAlpha(120)),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              if (toolName != null && toolName.isNotEmpty)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    toolName,
                    style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        fontFamily: 'monospace'),
                  ),
                ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _holding ? l10n.requestAwaiting : l10n.requestAtTerminal,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.4,
                    color: _holding ? Colors.amber.shade700 : theme.disabledColor,
                  ),
                ),
              ),
            ],
          ),

          // The content being reviewed.
          ...req.details.map((d) => _DetailBlock(detail: d, dense: widget.dense)),

          if (req.isQuestion) ..._buildQuestions(l10n),

          const SizedBox(height: 4),
          _buildActions(l10n),
        ],
      ),
    );
  }

  List<Widget> _buildQuestions(AppLocalizations l10n) {
    final questions = widget.request.questions;
    final widgets = <Widget>[];
    for (var i = 0; i < questions.length; i++) {
      final q = questions[i];
      widgets.add(Padding(
        padding: const EdgeInsets.only(top: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (q.header.isNotEmpty)
              Text(q.header.toUpperCase(),
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.6,
                    color: Theme.of(context).disabledColor,
                  )),
            if (q.question.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(q.question,
                    style: const TextStyle(fontSize: 13, height: 1.3)),
              ),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: q.options.map((o) {
                final key = '$i:${o.label}';
                final chosen = _selected.contains(key);
                return Tooltip(
                  message: o.description,
                  child: _OptionChip(
                    label: o.label,
                    selected: chosen,
                    selectable: !widget.request.isOneTap,
                    onTap: _busy ? null : () => _tapOption(i, o),
                  ),
                );
              }).toList(),
            ),
            const SizedBox(height: 6),
            TextField(
              controller: _controllerFor(i),
              enabled: !_busy,
              style: const TextStyle(fontSize: 13),
              decoration: InputDecoration(
                isDense: true,
                hintText: l10n.requestCustomAnswer,
                hintStyle: const TextStyle(fontSize: 12),
                border: const OutlineInputBorder(),
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
              ),
              onChanged: (_) => setState(() {
                // Typing is an alternative to picking, so drop the selection.
                _selected.removeWhere((k) => k.startsWith('$i:'));
              }),
            ),
          ],
        ),
      ));
    }
    return widgets;
  }

  Widget _buildActions(AppLocalizations l10n) {
    if (widget.request.isQuestion) {
      return Row(
        children: [
          FilledButton.tonal(
            onPressed: _busy || !_complete
                ? null
                : () => _run(() => widget.onRespond('allow', _collectAnswers())),
            child: Text(l10n.requestSubmit),
          ),
          const SizedBox(width: 8),
          TextButton(
            onPressed: _busy ? null : () => _run(() => widget.onRespond('deny', null)),
            child: Text(l10n.requestDeny),
          ),
        ],
      );
    }

    return Row(
      children: [
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: Colors.green.shade700),
          onPressed: _busy ? null : () => _run(() => widget.onRespond('allow', null)),
          child: Text(l10n.requestAllow),
        ),
        const SizedBox(width: 8),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
          onPressed: _busy ? null : () => _run(() => widget.onRespond('deny', null)),
          child: Text(l10n.requestDeny),
        ),
        const Spacer(),
        if (_busy)
          const SizedBox(
            width: 16,
            height: 16,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
      ],
    );
  }
}

class _OptionChip extends StatelessWidget {
  final String label;
  final bool selected;
  final bool selectable;
  final VoidCallback? onTap;

  const _OptionChip({
    required this.label,
    required this.selected,
    required this.selectable,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final highlight = selectable && selected;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: highlight
                ? theme.colorScheme.primary
                : theme.dividerColor,
            width: highlight ? 1.5 : 1,
          ),
          color: highlight
              ? theme.colorScheme.primary.withAlpha(30)
              : Colors.transparent,
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: highlight ? FontWeight.w600 : FontWeight.normal,
            color: highlight ? theme.colorScheme.primary : null,
          ),
        ),
      ),
    );
  }
}

/// One labelled block of the request's content.
class _DetailBlock extends StatelessWidget {
  final RequestDetail detail;
  final bool dense;

  const _DetailBlock({required this.detail, required this.dense});

  @override
  Widget build(BuildContext context) {
    final isDiff = detail.kind == 'diff';
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(detail.label.toUpperCase(),
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 0.6,
                    color: theme.disabledColor,
                  )),
              if (detail.truncated) ...[
                const SizedBox(width: 6),
                Text('·',
                    style: TextStyle(color: theme.disabledColor, fontSize: 10)),
                const SizedBox(width: 6),
                Text('truncated',
                    style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        color: Colors.orange.shade700)),
              ],
            ],
          ),
          const SizedBox(height: 4),
          Container(
            width: double.infinity,
            constraints: BoxConstraints(maxHeight: dense ? 140 : 260),
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerHighest.withAlpha(90),
              borderRadius: BorderRadius.circular(6),
            ),
            child: SingleChildScrollView(
              child: isDiff
                  ? _diffText(context)
                  : SelectableText(
                      detail.value,
                      style: TextStyle(
                        fontSize: detail.kind == 'text' ? 13 : 11.5,
                        height: 1.35,
                        fontFamily:
                            detail.kind == 'text' ? null : 'monospace',
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  /// The server sends the diff as one flat string with +/- prefixes, so the
  /// colouring happens here rather than every client parsing a richer shape.
  Widget _diffText(BuildContext context) {
    final spans = detail.value.split('\n').map((line) {
      final added = line.startsWith('+ ');
      final removed = line.startsWith('- ');
      return TextSpan(
        text: line,
        style: TextStyle(
          fontSize: 11.5,
          height: 1.35,
          fontFamily: 'monospace',
          color: added
              ? Colors.green.shade600
              : removed
                  ? Colors.red.shade600
                  : null,
        ),
      );
    }).toList();

    return SelectableText.rich(TextSpan(children: spans));
  }
}
