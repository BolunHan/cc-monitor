/**
 * dsh-cc-monitor — report DSH session activity to a cc-monitor server.
 *
 * The plugin subscribes to the DSH session event firehose and posts a
 * normalized Claude-Code-hook-shaped payload to /api/event. Configuration is
 * served over the plugin's own loopback-only /api/dsh-cc-monitor/config route
 * so it works independently of the DSH settings-namespace allowlist.
 */
import http from 'node:http';
import https from 'node:https';
import { randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';

const DEFAULT_HOST = '127.0.0.1';
const DEFAULT_PORT = 9876;
const CONFIG_FILE = join(homedir(), '.dsh', 'cc-monitor.json');

export const name = 'cc-monitor';

// Wait for the session store and web server before subscribing/registering.
export const inject = ['sessions', 'webServer'];

export function apply(ctx, config = {}) {
  let persisted = {};
  try {
    if (existsSync(CONFIG_FILE)) {
      persisted = JSON.parse(readFileSync(CONFIG_FILE, 'utf8'));
    }
  } catch {
    persisted = {};
  }

  if (!config.uid && !process.env.CC_MONITOR_UID && !persisted.uid) {
    persisted = { ...persisted, uid: `dsh-${randomUUID()}` };
    try {
      mkdirSync(dirname(CONFIG_FILE), { recursive: true });
      writeFileSync(CONFIG_FILE, JSON.stringify(persisted, null, 2));
    } catch {}
  }

  let current = () => ({ ...config, ...persisted });

  const currentConfig = () => {
    const value = current() ?? {};
    const rawPort = value.port ?? process.env.CC_MONITOR_PORT;
    const port = Number(rawPort ?? DEFAULT_PORT);
    return {
      enabled: value.enabled ?? true,
      serverUrl: value.serverUrl || process.env.CC_MONITOR_URL || '',
      host: value.host || process.env.CC_MONITOR_HOST || DEFAULT_HOST,
      port: Number.isFinite(port) && port > 0 ? port : DEFAULT_PORT,
      portExplicit: rawPort !== undefined && rawPort !== '',
      uid: value.uid || process.env.CC_MONITOR_UID || persisted.uid || `dsh-${randomUUID()}`,
    };
  };

  function normalizeConfig(input) {
    const port = Number(input?.port ?? DEFAULT_PORT);
    return {
      enabled: input?.enabled ?? true,
      serverUrl: input?.serverUrl ?? '',
      host: input?.host ?? DEFAULT_HOST,
      port: Number.isFinite(port) && port > 0 ? port : DEFAULT_PORT,
      uid: input?.uid || persisted.uid || `dsh-${randomUUID()}`,
    };
  }

  function saveConfig(patch) {
    const next = normalizeConfig({ ...currentConfig(), ...patch });
    persisted = next;
    mkdirSync(dirname(CONFIG_FILE), { recursive: true });
    writeFileSync(CONFIG_FILE, JSON.stringify(persisted, null, 2));
    return next;
  }

  function resolveServerUrl(cfg) {
    const urlOverride = cfg.serverUrl;
    const portOverride = cfg.port;

    if (urlOverride) {
      let base = String(urlOverride).trim();
      if (!/^https?:\/\//i.test(base)) base = `http://${base}`;
      const url = new URL(base);
      if (cfg.portExplicit && portOverride) url.port = String(portOverride);
      return url.toString().replace(/\/+$/, '');
    }

    const host = cfg.host || DEFAULT_HOST;
    const port = portOverride || DEFAULT_PORT;
    return `http://${host}:${port}`;
  }

  const serverUrl = () => resolveServerUrl(currentConfig());
  const uid = () => currentConfig().uid;

  function isLoopbackRequest(req) {
    const address = req.socket?.remoteAddress;
    if (address !== '127.0.0.1' && address !== '::1' && address !== '::ffff:127.0.0.1') return false;
    const host = req.headers.host;
    if (typeof host !== 'string') return false;
    let hostUrl;
    try { hostUrl = new URL(`http://${host}`); } catch { return false; }
    return hostUrl.hostname === '127.0.0.1' || hostUrl.hostname === 'localhost' || hostUrl.hostname === '[::1]';
  }

  function writeJson(res, status, body) {
    const payload = JSON.stringify(body);
    res.writeHead(status, {
      'content-type': 'application/json; charset=utf-8',
      'referrer-policy': 'no-referrer',
    });
    res.end(payload);
  }

  async function readJsonBody(req) {
    const chunks = [];
    let size = 0;
    for await (const chunk of req) {
      const buffer = chunk;
      size += buffer.length;
      if (size > 64 * 1024) return undefined;
      chunks.push(buffer);
    }
    try {
      const parsed = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      return typeof parsed === 'object' && parsed !== null ? parsed : undefined;
    } catch {
      return undefined;
    }
  }

  ctx.webServer.register({
    kind: 'exact',
    path: '/api/dsh-cc-monitor/config',
    handler: async (req, res) => {
      if (!isLoopbackRequest(req)) {
        writeJson(res, 403, { error: 'forbidden: loopback-only' });
        return;
      }
      if (req.method === 'GET') {
        writeJson(res, 200, currentConfig());
        return;
      }
      if (req.method === 'POST') {
        const body = await readJsonBody(req);
        if (body === undefined) {
          writeJson(res, 400, { error: 'invalid JSON body' });
          return;
        }
        const next = saveConfig(body);
        writeJson(res, 200, next);
        return;
      }
      writeJson(res, 405, { error: 'method not allowed' });
    },
  });

  // Map callId -> { name, arguments } so tool/result can report the tool name.
  const toolCalls = new Map();
  // Map sessionId -> { text, usage } for the most recent assistant message.
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
    return name.includes('ask_user') || name.includes('permission') || name.includes('approval');
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
      if (data.source?.kind !== 'user') return;
      const prompt = textFromBlocks(data.content);
      post({ ...basePayload(session), hook_event_name: 'UserPromptSubmit', prompt });
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
      toolCalls.set(data.callId, { name: data.name || 'tool', arguments: data.arguments || '' });
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
      post({ ...basePayload(session), hook_event_name: 'SessionEnd' });
      toolCalls.clear();
      lastAssistant.delete(sessionId);
    } catch (err) {
      console.warn('[dsh-cc-monitor] disposal report failed:', err?.message || err);
    }
  });
}
