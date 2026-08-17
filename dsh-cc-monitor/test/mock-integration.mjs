import http from 'node:http';
import assert from 'node:assert/strict';
import { apply } from '../lib/index.js';

const received = [];
const server = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/api/event') {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      try { received.push(JSON.parse(body)); } catch {}
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end('{}');
    });
  } else {
    res.writeHead(404);
    res.end();
  }
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const port = server.address().port;

const handlers = {};
const ctx = { on(event, cb) { handlers[event] = cb; } };
apply(ctx, { serverUrl: `http://127.0.0.1:${port}`, uid: 'test-uid' });

const session = { id: 'dsh-session-1', header: { cwd: '/tmp/dsh-project' } };
function fire(event) { handlers['session/event'](session, event); }

fire({ type: 'user/message', data: { source: { kind: 'user' }, content: [{ type: 'text', text: 'Refactor this code' }] } });
fire({ type: 'tool/call', data: { callId: 'call-1', name: 'ask_user_question', arguments: '{"question":"ok?"}' } });
fire({ type: 'tool/result', data: { message: { source: { kind: 'tool', callId: 'call-1' }, content: [{ type: 'text', text: 'yes' }] } } });
fire({ type: 'assistant/message', data: { message: { content: [{ type: 'text', text: 'Done' }] }, usage: { inputTokens: 10, outputTokens: 2, cacheReadTokens: 3 } } });
handlers['session/disposed'](session);

await new Promise((resolve) => setTimeout(resolve, 500));
server.close();

assert.equal(received.length, 5);
assert.equal(received[0].hook_event_name, 'UserPromptSubmit');
assert.equal(received[0].prompt, 'Refactor this code');
assert.equal(received[0].agent, 'dsh');
assert.equal(received[0].cc_monitor_uid, 'test-uid');
assert.equal(received[1].hook_event_name, 'PermissionRequest');
assert.equal(received[2].hook_event_name, 'PostToolUse');
assert.equal(received[2].tool_name, 'ask_user_question');
assert.equal(received[3].hook_event_name, 'Stop');
assert.equal(received[3].usage.input_tokens, 13);
assert.equal(received[4].hook_event_name, 'SessionEnd');
console.log('dsh-cc-monitor mock integration: OK', received.map((r) => r.hook_event_name).join(','));
