/**
 * dsh-cc-monitor — report DSH session activity to a cc-monitor server.
 *
 * The plugin subscribes to the DSH session event firehose and posts a
 * normalized Claude-Code-hook-shaped payload to /api/event. The server
 * already understands those events; the `agent` field tells it (and every
 * dashboard) that this session belongs to DSH rather than Claude Code.
 *
 * Configuration (all optional):
 *   config.serverUrl — cc-monitor server base URL (full override)
 *   config.host      — server host, used when serverUrl is not set
 *   config.port      — server port, overrides the URL port when set
 *   config.uid       — installation identifier sent as cc_monitor_uid
 *   config.enabled   — master switch (default true)
 *
 * Environment fallbacks:
 *   CC_MONITOR_URL, CC_MONITOR_HOST, CC_MONITOR_PORT, CC_MONITOR_UID.
 */
import http from 'node:http';
import https from 'node:https';

const DEFAULT_HOST = '127.0.0.1';
const DEFAULT_PORT = 9876;

export const name = 'cc-monitor';

// Wait for the session store before subscribing to its events.
export const inject = ['sessions'];

export function apply(ctx, config = {}) {
  if (config.enabled === false) return;

  const serverUrl = resolveServerUrl(config);
  const uid = config.uid || process.env.CC_MONITOR_UID || 'dsh-default';

  function resolveServerUrl(cfg) {
    const urlOverride = cfg.serverUrl || process.env.CC_MONITOR_URL;
    const portOverride = cfg.port || process.env.CC_MONITOR_PORT;

    if (urlOverride) {
      let base = String(urlOverride).trim();
      if (!/^https?:\/\//i.test(base)) base = `http://${base}`;
      const url = new URL(base);
      if (portOverride) url.port = String(portOverride);
      return url.toString().replace(/\/+$/, '');
    }

    const host = cfg.host || process.env.CC_MONITOR_HOST || DEFAULT_HOST;
    const port = portOverride || DEFAULT_PORT;
    return `http://${host}:${port}`;
  }

  // Map callId -> { name, arguments } so tool/result can report the tool name.
  const toolCalls = new Map();

  function candidateUrls() {
    if (serverUrl.startsWith('https://')) {
      return [serverUrl, serverUrl.replace('https://', 'http://')];
    }
    if (serverUrl.startsWith('http://')) {
      return [serverUrl, serverUrl.replace('http://', 'https://')];
    }
    return [`https://${serverUrl}`, `http://${serverUrl}`];
  }

  function postOnce(baseUrl, payload) {
    return new Promise((resolve, reject) => {
      const target = new URL(`${baseUrl}/api/event`);
      const isHttps = target.protocol === 'https:';
      const lib = isHttps ? https : http;
      const data = Buffer.from(JSON.stringify(payload));

      const req = lib.request({
        hostname: target.hostname,
        port: target.port || (isHttps ? 443 : 80),
        path: `${target.pathname}${target.search}`,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': data.length,
        },
        // cc-monitor in LAN/Docker mode serves a self-signed cert.
        rejectUnauthorized: false,
        timeout: 2500,
      }, (res) => {
        res.resume();
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve();
        } else {
          reject(new Error(`cc-monitor returned HTTP ${res.statusCode}`));
        }
      });

      req.on('timeout', () => req.destroy(new Error('cc-monitor request timed out')));
      req.on('error', reject);
      req.end(data);
    });
  }

  function post(payload) {
    (async () => {
      let lastError;
      for (const baseUrl of candidateUrls()) {
        try {
          await postOnce(baseUrl, payload);
          return;
        } catch (err) {
          lastError = err;
        }
      }
      // Reporting is best-effort: never break an agent turn because the
      // dashboard server is down or unreachable.
      console.warn('[dsh-cc-monitor] report failed:', lastError?.message || lastError);
    })();
  }

  function textFromBlocks(blocks) {
    if (!Array.isArray(blocks)) return '';
    return blocks.map((block) => {
      if (!block || typeof block !== 'object') return '';
      if (block.type === 'text') return block.text || '';
      if (block.type === 'reasoning') return block.reasoning || block.text || '';
      if (block.type === 'tool-call') return block.name || '';
      if (block.type === 'tool-result') return textFromBlocks(block.content);
      return block.text || block.content || '';
    }).filter(Boolean).join('\n').trim();
  }

  function usageToClaudeShape(usage) {
    if (!usage || typeof usage !== 'object') return undefined;
    const inputTokens =
      (usage.inputTokens || 0) +
      (usage.cacheReadTokens || 0) +
      (usage.cacheWriteTokens || 0);
    return {
      input_tokens: inputTokens || undefined,
      output_tokens: usage.outputTokens || undefined,
    };
  }

  function isApprovalTool(toolName) {
    const name = String(toolName || '').toLowerCase();
    return name.includes('ask_user') ||
      name.includes('permission') ||
      name.includes('approval');
  }

  function basePayload(session) {
    return {
      session_id: String(session.id),
      cwd: session.header?.cwd || process.cwd(),
      agent: 'dsh',
      cc_monitor_uid: uid,
    };
  }

  function handleSessionEvent(session, event) {
    const data = event?.data || {};

    if (event.type === 'user/message') {
      // Only direct human prompts become a card summary; injected context
      // (file-change notices, skill catalogs, goal-round injections) is not
      // user work and would otherwise overwrite the visible prompt.
      if (data.source?.kind !== 'user') return;
      const prompt = textFromBlocks(data.content);
      post({
        ...basePayload(session),
        hook_event_name: 'UserPromptSubmit',
        prompt,
      });
      return;
    }

    if (event.type === 'assistant/message') {
      const message = data.message || {};
      post({
        ...basePayload(session),
        hook_event_name: 'Stop',
        last_assistant_message: textFromBlocks(message.content),
        usage: usageToClaudeShape(data.usage),
      });
      return;
    }

    if (event.type === 'tool/call') {
      toolCalls.set(data.callId, {
        name: data.name || 'tool',
        arguments: data.arguments || '',
      });
      if (toolCalls.size > 500) {
        const oldest = toolCalls.keys().next().value;
        toolCalls.delete(oldest);
      }
      post({
        ...basePayload(session),
        hook_event_name: isApprovalTool(data.name) ? 'PermissionRequest' : 'PreToolUse',
        tool_name: data.name || 'tool',
        tool_input: data.arguments || '',
      });
      return;
    }

    if (event.type === 'tool/result') {
      const message = data.message || {};
      const callId = message.source?.callId;
      const call = (callId && toolCalls.get(callId)) || {};
      post({
        ...basePayload(session),
        hook_event_name: 'PostToolUse',
        tool_name: call.name || 'tool',
        tool_input: call.arguments || '',
        tool_output: textFromBlocks(message.content),
      });
      return;
    }

    if (event.type === 'turn/end' && data.reason?.kind === 'error') {
      post({
        ...basePayload(session),
        hook_event_name: 'Stop',
        last_assistant_message: `Turn ended with error: ${data.reason?.error || data.reason?.kind || 'unknown'}`,
      });
    }
  }

  ctx.on('session/event', (session, event) => {
    try {
      handleSessionEvent(session, event);
    } catch (err) {
      console.warn('[dsh-cc-monitor] event handling failed:', err?.message || err);
    }
  });

  ctx.on('session/disposed', (session) => {
    try {
      post({
        ...basePayload(session),
        hook_event_name: 'SessionEnd',
      });
      toolCalls.clear();
    } catch (err) {
      console.warn('[dsh-cc-monitor] disposal report failed:', err?.message || err);
    }
  });
}

