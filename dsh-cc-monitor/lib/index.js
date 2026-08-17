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
import { installSettingsSection, settingsNamespace } from '@deepseek-ai/dsh-settings';
import z from 'schemastery';

const DEFAULT_HOST = '127.0.0.1';
const DEFAULT_PORT = 9876;

export const name = 'cc-monitor';

// Wait for the session store before subscribing to its events.
export const inject = ['sessions'];

/** Settings namespace the Web UI settings card edits. */
export const CC_MONITOR_SETTINGS_NAMESPACE = settingsNamespace('cc-monitor');

/** Runtime schema for {@link Config}. */
export const ConfigSchema = z.object({
  enabled: z.boolean().default(true),
  serverUrl: z.string().default(''),
  host: z.string().default('127.0.0.1'),
  port: z.number().step(1).min(1).max(65535).default(9876),
  uid: z.string().default('dsh-default'),
});

export function apply(ctx, config = {}) {
  let current = () => config ?? {};

  const currentConfig = () => {
    const value = current() ?? {};
    return {
      enabled: value.enabled ?? true,
      serverUrl: value.serverUrl || process.env.CC_MONITOR_URL,
      host: value.host || process.env.CC_MONITOR_HOST || DEFAULT_HOST,
      port: value.port || process.env.CC_MONITOR_PORT || DEFAULT_PORT,
      uid: value.uid || process.env.CC_MONITOR_UID || 'dsh-default',
    };
  };

  function resolveServerUrl(cfg) {
    const urlOverride = cfg.serverUrl;
    const portOverride = cfg.port;

    if (urlOverride) {
      let base = String(urlOverride).trim();
      if (!/^https?:\/\//i.test(base)) base = `http://${base}`;
      const url = new URL(base);
      if (portOverride) url.port = String(portOverride);
      return url.toString().replace(/\/+$/, '');
    }

    const host = cfg.host || DEFAULT_HOST;
    const port = portOverride || DEFAULT_PORT;
    return `http://${host}:${port}`;
  }

  const serverUrl = () => resolveServerUrl(currentConfig());
  const uid = () => currentConfig().uid;

  installSettingsSection(ctx, CC_MONITOR_SETTINGS_NAMESPACE, ConfigSchema, config ?? {}, {
    setSource: (source) => { current = source; },
    onChange: () => {},
  });

  // Map callId -> { name, arguments } so tool/result can report the tool name.
  const toolCalls = new Map();
  // Map sessionId -> { text, usage } for the most recent assistant message.
  // DSH emits assistant/message for every step (including tool-calling steps),
  // so we defer the cc-monitor Stop until turn/end and only use the final
  // text-only assistant content as the response summary.
  const lastAssistant = new Map();

  function candidateUrls() {
    const base = serverUrl();
    if (base.startsWith('https://')) {
      return [base, base.replace('https://', 'http://')];
    }
    if (base.startsWith('http://')) {
      return [base, base.replace('http://', 'https://')];
    }
    return [`https://${base}`, `http://${base}`];
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
    if (!currentConfig().enabled) return;
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

  function assistantTextFromBlocks(blocks) {
    if (!Array.isArray(blocks)) return '';
    return blocks.map((block) => {
      if (!block || typeof block !== 'object') return '';
      if (block.type === 'text') return block.text || '';
      return '';
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
      cc_monitor_uid: uid(),
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
      lastAssistant.set(String(session.id), {
        text: assistantTextFromBlocks(message.content),
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

    if (event.type === 'turn/end') {
      const sessionId = String(session.id);
      const last = lastAssistant.get(sessionId) || {};
      lastAssistant.delete(sessionId);

      let lastMessage = last.text || '';
      if (data.reason?.kind === 'error') {
        lastMessage = `Turn ended with error: ${data.reason?.error || data.reason?.kind || 'unknown'}`;
      }

      post({
        ...basePayload(session),
        hook_event_name: 'Stop',
        last_assistant_message: lastMessage,
        usage: last.usage,
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
      const sessionId = String(session.id);
      post({
        ...basePayload(session),
        hook_event_name: 'SessionEnd',
      });
      toolCalls.clear();
      lastAssistant.delete(sessionId);
    } catch (err) {
      console.warn('[dsh-cc-monitor] disposal report failed:', err?.message || err);
    }
  });
}

