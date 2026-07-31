import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:cc_monitor_app/l10n/app_localizations.dart';
import '../app_theme.dart';
import '../models/session.dart';
import '../models/session_stats.dart';
import '../models/message.dart';
import '../providers/session_provider.dart';

class SessionDetailScreen extends StatefulWidget {
  final String sessionId;

  const SessionDetailScreen({super.key, required this.sessionId});

  @override
  State<SessionDetailScreen> createState() => _SessionDetailScreenState();
}

class _SessionDetailScreenState extends State<SessionDetailScreen> {
  SessionStats? _stats;
  /// Messages stored **newest-first** (matching server order).
  /// With reverse:true, index 0 = bottom, last index = top.
  final List<Message> _messages = [];
  int _totalMessages = 0;
  bool _loading = false;
  bool _allLoaded = false;
  int _highlightCount = 0;
  final ScrollController _scrollCtrl = ScrollController();
  static const int _pageSize = 10;

  @override
  void initState() {
    super.initState();
    _scrollCtrl.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadData());
  }

  @override
  void dispose() {
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    super.dispose();
  }

  /// With reverse:true, maxScrollExtent = top of list (oldest).
  /// pixels approaching maxScrollExtent means we're near the top.
  void _onScroll() {
    if (!_scrollCtrl.hasClients) return;
    final max = _scrollCtrl.position.maxScrollExtent;
    if (max <= 0) return;
    // Within 200px of the top → load older messages
    if ((max - _scrollCtrl.position.pixels) < 200 &&
        !_loading &&
        !_allLoaded) {
      _loadMore();
    }
  }

  Future<void> _loadData() async {
    final provider = context.read<SessionProvider>();
    final stats = await provider.fetchStats(widget.sessionId);
    if (!mounted) return;
    setState(() => _stats = stats);
    await _loadMessages(offset: 0);
    await _ensureScroller();
  }

  Future<void> _loadMessages({required int offset}) async {
    if (_loading) return;
    setState(() => _loading = true);

    final provider = context.read<SessionProvider>();
    final result = await provider.fetchMessages(widget.sessionId,
        offset: offset, limit: _pageSize);

    if (!mounted) return;
    if (result != null) {
      // Server returns newest-first; we store newest-first for reverse:true
      final batch = result.messages;
      final isFirstBatch = offset == 0;

      setState(() {
        if (isFirstBatch) {
          _messages.clear();
          _messages.addAll(batch);
        } else {
          // Append older messages at the end (they render at the top)
          final oldLen = _messages.length;
          _messages.addAll(batch);
          _highlightCount = _messages.length - oldLen;
        }
        _totalMessages = result.total;
        _allLoaded = _messages.length >= result.total;
        _loading = false;
      });

      if (!isFirstBatch && _highlightCount > 0) {
        Future.delayed(const Duration(milliseconds: 800), () {
          if (mounted) setState(() => _highlightCount = 0);
        });
      }
    } else {
      setState(() => _loading = false);
    }
  }

  Future<void> _loadMore() async {
    await _loadMessages(offset: _messages.length);
  }

  /// Keep loading until the list overflows (scrollbar appears) or all loaded.
  Future<void> _ensureScroller() async {
    for (int i = 0; i < 10; i++) {
      if (!mounted || _allLoaded) break;
      await Future.delayed(const Duration(milliseconds: 200));
      if (!mounted || _allLoaded) break;
      try {
        if (_scrollCtrl.hasClients &&
            _scrollCtrl.position.maxScrollExtent > 20) break;
      } catch (_) {
        break;
      }
      await _loadMessages(offset: _messages.length);
    }
  }

  /// Newest-first index → reverse:true display index.
  /// With reverse:true, ListView renders item 0 at the bottom.
  /// Our _messages[0] = newest → should be at bottom ✓
  /// _messages[last] = oldest → should be at top ✓
  /// So reverse:true itemIndex maps directly to _messages index:
  ///   display index 0 = _messages[0] = newest = bottom ✓

  Session? _findSession(SessionProvider provider) {
    return [...provider.active, ...provider.complete, ...provider.archived]
        .where((s) => s.sessionId == widget.sessionId)
        .firstOrNull;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Consumer<SessionProvider>(
      builder: (context, provider, _) {
        final session = _findSession(provider);
        if (session == null) {
          return Scaffold(
            appBar: AppBar(title: Text(l10n.sessionTitle)),
            body: Center(child: Text(l10n.sessionNotFound)),
          );
        }

        return Scaffold(
          appBar: AppBar(
            title: Row(
              children: [
                Flexible(
                  child: Text(
                    session.summary?.isNotEmpty == true
                        ? session.summary!
                        : _dirBasename(session.cwd),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                _StateBadge(state: session.state),
              ],
            ),
          ),
          body: Column(
            children: [
              if (_stats != null) _StatsBar(stats: _stats!, l10n: l10n),
              if (_stats != null && _stats!.toolBreakdown.isNotEmpty)
                _ToolChips(stats: _stats!, l10n: l10n),
              if (_totalMessages > 0)
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  child: Row(
                    children: [
                      Text(
                        '${_messages.length} / $_totalMessages messages',
                        style: const TextStyle(
                            fontSize: 11, color: Colors.grey),
                      ),
                      const Spacer(),
                      if (_loading)
                        const SizedBox(
                          width: 12,
                          height: 12,
                          child: CircularProgressIndicator(strokeWidth: 1.5),
                        ),
                    ],
                  ),
                ),
              const Divider(height: 1),
              Expanded(child: _buildTimeline(l10n)),
            ],
          ),
        );
      },
    );
  }

  Widget _buildTimeline(AppLocalizations l10n) {
    if (_messages.isEmpty && _loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_messages.isEmpty) {
      return Center(child: Text(l10n.noSessions));
    }

    // reverse:true — item 0 at bottom (newest), item N-1 at top (oldest)
    // _messages is newest-first, so _messages[0] = bottom ✓
    // When we append older messages to end of _messages, they render at top.
    // _highlightCount marks the N newest-appended items (at end of list = top).
    final highlightStart = _messages.length - _highlightCount;

    return ListView.builder(
      reverse: true,
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      itemCount: _messages.length + (_allLoaded ? 1 : 0),
      itemBuilder: (context, index) {
        // With reverse:true, index 0 = bottom of screen
        // End marker at the very top when all loaded
        if (_allLoaded && index == _messages.length) {
          return _EndMarker(total: _totalMessages, l10n: l10n);
        }
        if (index >= _messages.length) return const SizedBox.shrink();
        final msg = _messages[index];
        final highlight = index >= highlightStart && _highlightCount > 0;
        return _TimelineMsg(
          msg: msg,
          l10n: l10n,
          highlight: highlight,
        );
      },
    );
  }

  String _dirBasename(String cwd) {
    if (cwd.isEmpty) return '';
    final trimmed = cwd.endsWith('/') ? cwd.substring(0, cwd.length - 1) : cwd;
    final idx = trimmed.lastIndexOf('/');
    return idx >= 0 ? trimmed.substring(idx + 1) : trimmed;
  }
}

// ---- State badge ----

class _StateBadge extends StatelessWidget {
  final String state;
  const _StateBadge({required this.state});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: AppTheme.stateBgColor(state),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(
          color: AppTheme.stateColor(state).withAlpha(100),
          width: 0.5,
        ),
      ),
      child: Text(
        _label(l10n),
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w600,
          color: AppTheme.stateColor(state),
        ),
      ),
    );
  }

  String _label(AppLocalizations l10n) {
    return switch (state) {
      'working' => l10n.stateWorking,
      'idle' => l10n.stateIdle,
      'pending_approval' => l10n.statePendingApproval,
      'pending_review' => l10n.statePendingReview,
      'all_done' => l10n.stateAllDone,
      _ => l10n.stateArchived,
    };
  }
}

// ---- Stats bar ----

class _StatsBar extends StatelessWidget {
  final SessionStats stats;
  final AppLocalizations l10n;
  const _StatsBar({required this.stats, required this.l10n});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      child: Wrap(
        spacing: 6,
        runSpacing: 4,
        children: [
          _StatChip('prompts', '${stats.totalPrompts}'),
          _StatChip('responses', '${stats.totalAssistantMessages}'),
          _StatChip('tool calls', '${stats.totalToolCalls}'),
          _StatChip('input tokens',
              stats.totalInputTokens > 0 ? _fmt(stats.totalInputTokens) : '—'),
          _StatChip('output tokens',
              stats.totalOutputTokens > 0
                  ? _fmt(stats.totalOutputTokens)
                  : '—'),
          _StatChip('duration', stats.formattedDuration),
          _StatChip('storage', stats.formattedSize),
        ],
      ),
    );
  }

  String _fmt(int n) {
    if (n >= 1000000) return '${(n / 1000000).toStringAsFixed(1)}M';
    if (n >= 1000) return '${(n ~/ 1000)}k';
    return '$n';
  }
}

class _StatChip extends StatelessWidget {
  final String label, value;
  const _StatChip(this.label, this.value);

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: isDark ? Colors.white10 : Colors.black.withAlpha(12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(
          color: isDark ? Colors.white12 : Colors.black.withAlpha(25),
        ),
      ),
      child: Text(
        '$label $value',
        style: TextStyle(
          fontSize: 11,
          color: isDark ? Colors.white70 : Colors.black87,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}

// ---- Tool chips ----

class _ToolChips extends StatelessWidget {
  final SessionStats stats;
  final AppLocalizations l10n;
  const _ToolChips({required this.stats, required this.l10n});

  @override
  Widget build(BuildContext context) {
    final entries = stats.toolBreakdown.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 4),
      child: Wrap(
        spacing: 4,
        runSpacing: 2,
        children: entries
            .map((e) => Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppTheme.stateColor('working').withAlpha(20),
                    borderRadius: BorderRadius.circular(3),
                    border: Border.all(
                      color: AppTheme.stateColor('working').withAlpha(40),
                    ),
                  ),
                  child: Text(
                    '${e.key} ×${e.value}',
                    style: TextStyle(
                      fontSize: 10,
                      color: AppTheme.stateColor('working'),
                    ),
                  ),
                ))
            .toList(),
      ),
    );
  }
}

// ---- End marker ----

class _EndMarker extends StatelessWidget {
  final int total;
  final AppLocalizations l10n;
  const _EndMarker({required this.total, required this.l10n});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Column(
      children: [
        const SizedBox(height: 4),
        Divider(color: isDark ? Colors.white12 : Colors.black12),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Text(
            'Beginning of conversation · $total messages',
            style: TextStyle(
              fontSize: 11,
              color: isDark ? Colors.white38 : Colors.black45,
            ),
          ),
        ),
      ],
    );
  }
}

// ---- Timeline message ----

class _TimelineMsg extends StatelessWidget {
  final Message msg;
  final AppLocalizations l10n;
  final bool highlight;
  const _TimelineMsg({
    required this.msg,
    required this.l10n,
    this.highlight = false,
  });

  @override
  Widget build(BuildContext context) {
    final utc = DateTime.fromMillisecondsSinceEpoch(
        (msg.timestamp * 1000).round(),
        isUtc: true);
    final local = utc.toLocal();
    final now = DateTime.now();
    final isToday = local.year == now.year &&
        local.month == now.month &&
        local.day == now.day;
    final timeStr = isToday
        ? 'Today ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}'
        : '${local.year}-${local.month.toString().padLeft(2, '0')}-${local.day.toString().padLeft(2, '0')} ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final borderColor = isDark ? Colors.white12 : Colors.black12;

    String typeLabel;
    IconData icon;
    Color dotColor;
    Color cardColor;
    String? tokenLabel;
    switch (msg.type) {
      case 'user_prompt':
        typeLabel = 'Prompt';
        icon = Icons.arrow_upward;
        dotColor = AppTheme.stateColor('pending_approval');
        cardColor = AppTheme.stateColor('pending_approval').withAlpha(15);
        tokenLabel = _fmtToken(msg.inputTokens);
        break;
      case 'assistant_response':
        typeLabel = 'Response';
        icon = Icons.arrow_downward;
        dotColor = AppTheme.stateColor('all_done');
        cardColor = AppTheme.stateColor('all_done').withAlpha(15);
        tokenLabel = _fmtToken(msg.outputTokens);
        break;
      case 'thinking':
        typeLabel = 'Thinking';
        icon = Icons.psychology;
        dotColor = Colors.grey;
        cardColor = Colors.transparent;
        tokenLabel = _fmtToken(msg.inputTokens);
        break;
      default:
        typeLabel = 'Tool';
        icon = Icons.build;
        dotColor = AppTheme.stateColor('working');
        cardColor = AppTheme.stateColor('working').withAlpha(12);
        tokenLabel = _fmtToken(
            (msg.inputTokens ?? 0) + (msg.outputTokens ?? 0));
    }

    final metaCard = Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 3),
      decoration: BoxDecoration(
        color: isDark ? Colors.white10 : Colors.black.withAlpha(8),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: borderColor, width: 0.5),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(timeStr,
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  color: isDark ? Colors.white60 : Colors.black54)),
          const SizedBox(height: 1),
          Text(typeLabel,
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 7,
                  fontWeight: FontWeight.w600,
                  color: dotColor)),
          if (tokenLabel != null) ...[
            const SizedBox(height: 1),
            Text(tokenLabel!,
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontSize: 7,
                    color: isDark ? Colors.white38 : Colors.black38)),
          ],
        ],
      ),
    );

    // Thinking gets a minimal row — no card
    if (msg.type == 'thinking') {
      return AnimatedContainer(
        duration: const Duration(milliseconds: 600),
        curve: Curves.easeOut,
        color: highlight
            ? (isDark ? Colors.white.withAlpha(12) : Colors.black.withAlpha(8))
            : Colors.transparent,
        child: Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            children: [
              SizedBox(width: 56, child: Padding(
                padding: const EdgeInsets.only(right: 6),
                child: metaCard,
              )),
              const SizedBox(width: 28, child: Center(
                child: Icon(Icons.psychology, size: 14, color: Colors.grey),
              )),
              const Expanded(
                child: Padding(
                  padding: EdgeInsets.only(left: 8, top: 4),
                  child: Text('Thinking…',
                      style: TextStyle(fontSize: 12, color: Colors.grey,
                          fontStyle: FontStyle.italic)),
                ),
              ),
            ],
          ),
        ),
      );
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 600),
      curve: Curves.easeOut,
      color: highlight
          ? (isDark ? Colors.white.withAlpha(12) : Colors.black.withAlpha(8))
          : Colors.transparent,
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 56,
              child: Padding(
                padding: const EdgeInsets.only(right: 6, top: 2),
                child: metaCard,
              ),
            ),
            SizedBox(
              width: 28,
              child: Column(
                children: [
                  Container(
                    width: 20,
                    height: 20,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: Theme.of(context).scaffoldBackgroundColor,
                      border: Border.all(color: dotColor, width: 2),
                    ),
                    child: Icon(icon, size: 11, color: dotColor),
                  ),
                  Expanded(
                    child: Container(width: 2, color: borderColor),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: cardColor,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: dotColor.withAlpha(50),
                      width: 0.5,
                    ),
                  ),
                  child: _buildCardContent(isDark),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCardContent(bool isDark) {
    if (msg.isTool) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            msg.toolName ?? 'tool',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: isDark ? Colors.white : Colors.black87,
            ),
          ),
          if (msg.toolInput != null && msg.toolInput!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                _truncate(msg.toolInput!, 200),
                style: TextStyle(
                    fontSize: 11,
                    color: isDark ? Colors.white54 : Colors.black54),
              ),
            ),
          if (msg.toolOutput != null && msg.toolOutput!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                '→ ${_truncate(msg.toolOutput!, 200)}',
                style: TextStyle(
                    fontSize: 11,
                    color: isDark ? Colors.white54 : Colors.black54),
              ),
            ),
        ],
      );
    }
    return Text(
      msg.content?.isNotEmpty == true ? msg.content! : '(empty)',
      style: TextStyle(
        fontSize: 13,
        color: isDark ? Colors.white : Colors.black87,
        height: 1.4,
      ),
    );
  }

  static String? _fmtToken(int? tokens) {
    if (tokens == null || tokens == 0) return null;
    if (tokens >= 1000) return 'est. ${(tokens / 1000).toStringAsFixed(1)}k';
    return 'est. $tokens';
  }

  String _truncate(String s, int maxLen) {
    if (s.length <= maxLen) return s;
    return '${s.substring(0, maxLen)}…';
  }
}
