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
  final List<Message> _messages = [];
  int _totalMessages = 0;
  bool _loadingMessages = false;
  bool _allLoaded = false;
  bool _initialLoadDone = false;
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

  void _onScroll() {
    if (_scrollCtrl.position.pixels < 80 &&
        !_loadingMessages &&
        !_allLoaded) {
      _loadMore();
    }
  }

  Future<void> _loadData() async {
    final provider = context.read<SessionProvider>();
    final stats = await provider.fetchStats(widget.sessionId);
    if (!mounted) return;
    setState(() => _stats = stats);

    // Load initial batch
    await _loadMessages(offset: 0);

    // Ensure scrollbar fills viewport
    await _ensureScroller();

    // Final scroll to very bottom
    if (mounted && _messages.isNotEmpty) {
      _initialLoadDone = true;
      // Double post-frame to guarantee layout is complete
      WidgetsBinding.instance.addPostFrameCallback((_) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollCtrl.hasClients && mounted) {
            _scrollCtrl.jumpTo(_scrollCtrl.position.maxScrollExtent);
          }
        });
      });
    }
  }

  Future<void> _loadMessages({required int offset}) async {
    if (_loadingMessages) return;
    setState(() => _loadingMessages = true);

    final provider = context.read<SessionProvider>();
    final result = await provider.fetchMessages(widget.sessionId,
        offset: offset, limit: _pageSize);

    if (!mounted) return;
    if (result != null) {
      final ordered = result.messages.reversed.toList();

      // Capture scroll state BEFORE mutating data
      final double prevPixels =
          _scrollCtrl.hasClients ? _scrollCtrl.position.pixels : 0.0;
      final double prevMax =
          _scrollCtrl.hasClients ? _scrollCtrl.position.maxScrollExtent : 0.0;
      final bool wasAtBottom = prevMax > 0 &&
          (prevMax - prevPixels) < 50; // within 50px of bottom

      setState(() {
        if (offset == 0) {
          _messages.clear();
          _messages.addAll(ordered);
        } else {
          _messages.insertAll(0, ordered);
          _highlightCount = ordered.length; // flash newly prepended messages
        }
        _totalMessages = result.total;
        _allLoaded = _messages.length >= result.total;
        _loadingMessages = false;
      });

      // Clear highlight after animation
      if (offset > 0) {
        Future.delayed(const Duration(milliseconds: 800), () {
          if (mounted) setState(() => _highlightCount = 0);
        });
      }

      // Position handling — defer to after layout
      if (offset > 0 && _scrollCtrl.hasClients) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!_scrollCtrl.hasClients || !mounted) return;
            if (wasAtBottom) {
              _scrollCtrl.jumpTo(_scrollCtrl.position.maxScrollExtent);
            } else {
              final newMax = _scrollCtrl.position.maxScrollExtent;
              final delta = newMax - prevMax;
              if (delta > 0) {
                _scrollCtrl.jumpTo(prevPixels + delta);
              }
            }
          });
        });
      }
    } else {
      setState(() => _loadingMessages = false);
    }
  }

  Future<void> _loadMore() async {
    await _loadMessages(offset: _messages.length);
  }

  Future<void> _ensureScroller() async {
    for (int i = 0; i < 10; i++) {
      if (!mounted || _allLoaded) break;
      await Future.delayed(const Duration(milliseconds: 200));
      if (!mounted || _allLoaded) break;
      try {
        if (_scrollCtrl.hasClients &&
            _scrollCtrl.position.maxScrollExtent > 10) break;
      } catch (_) {
        break;
      }
      await _loadMessages(offset: _messages.length);
    }
  }

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
                      if (_loadingMessages)
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
    if (_messages.isEmpty && _loadingMessages) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_messages.isEmpty) {
      return Center(child: Text(l10n.noSessions));
    }
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      itemCount: _messages.length + (_allLoaded ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == 0 && _allLoaded) {
          return _EndMarker(total: _totalMessages, l10n: l10n);
        }
        final msgIndex = _allLoaded ? index - 1 : index;
        if (msgIndex < 0 || msgIndex >= _messages.length) {
          return const SizedBox.shrink();
        }
        final highlight = msgIndex < _highlightCount;
        return _TimelineMsg(
          msg: _messages[msgIndex],
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
    final time = DateTime.fromMillisecondsSinceEpoch(
        (msg.timestamp * 1000).round(),
        isUtc: true);
    final timeStr =
        '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final borderColor = isDark ? Colors.white12 : Colors.black12;

    String typeLabel;
    IconData icon;
    Color dotColor;
    Color cardColor;
    switch (msg.type) {
      case 'user_prompt':
        typeLabel = 'Prompt';
        icon = Icons.arrow_upward;
        dotColor = AppTheme.stateColor('pending_approval');
        cardColor = AppTheme.stateColor('pending_approval').withAlpha(15);
        break;
      case 'assistant_response':
        typeLabel = 'Response';
        icon = Icons.arrow_downward;
        dotColor = AppTheme.stateColor('all_done');
        cardColor = AppTheme.stateColor('all_done').withAlpha(15);
        break;
      default: // tool_use
        typeLabel = 'Tool';
        icon = Icons.build;
        dotColor = AppTheme.stateColor('working');
        cardColor = AppTheme.stateColor('working').withAlpha(12);
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
            // Meta badge
            SizedBox(
              width: 56,
              child: Padding(
                padding: const EdgeInsets.only(right: 6, top: 2),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 4, vertical: 2),
                      decoration: BoxDecoration(
                        color: isDark
                            ? Colors.white10
                            : Colors.black.withAlpha(8),
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(color: borderColor, width: 0.5),
                      ),
                      child: Column(
                        children: [
                          Text(timeStr,
                              style: TextStyle(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w600,
                                  color: isDark
                                      ? Colors.white60
                                      : Colors.black54)),
                          Text(typeLabel,
                              style: TextStyle(
                                  fontSize: 7,
                                  fontWeight: FontWeight.w600,
                                  color: dotColor)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // Gutter: dot + line
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
                    child: Container(
                      width: 2,
                      color: borderColor,
                    ),
                  ),
                ],
              ),
            ),
            // Card
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
                  color: isDark ? Colors.white54 : Colors.black54,
                ),
              ),
            ),
          if (msg.toolOutput != null && msg.toolOutput!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                '→ ${_truncate(msg.toolOutput!, 200)}',
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? Colors.white54 : Colors.black54,
                ),
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

  String _truncate(String s, int maxLen) {
    if (s.length <= maxLen) return s;
    return '${s.substring(0, maxLen)}…';
  }
}
