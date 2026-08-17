import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:cc_monitor_app/models/session.dart';
import 'package:cc_monitor_app/widgets/agent_badge.dart';

void main() {
  test('Session.fromJson defaults agent to claude', () {
    final session = Session.fromJson({
      'session_id': 's1',
      'cwd': '/tmp',
      'state': 'idle',
      'raw_event': 'Stop',
      'updated_at': '2026-08-17T00:00:00.000000Z',
    });
    expect(session.agent, 'claude');
  });

  test('Session.fromJson preserves dsh agent', () {
    final session = Session.fromJson({
      'session_id': 's2',
      'cwd': '/tmp',
      'state': 'working',
      'raw_event': 'UserPromptSubmit',
      'agent': 'dsh',
      'updated_at': '2026-08-17T00:00:00.000000Z',
    });
    expect(session.agent, 'dsh');
  });

  testWidgets('AgentBadge shows CC for Claude sessions', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: AgentBadge(agent: 'claude')),
    ));
    expect(find.text('CC'), findsOneWidget);
    expect(find.text('DSH'), findsNothing);
  });

  testWidgets('AgentBadge shows DSH for DSH sessions', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: AgentBadge(agent: 'dsh')),
    ));
    expect(find.text('DSH'), findsOneWidget);
    expect(find.text('CC'), findsNothing);
  });

  testWidgets('AgentBadge defaults to CC for legacy sessions', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: AgentBadge()),
    ));
    expect(find.text('CC'), findsOneWidget);
  });
}
