window.__ModuleLoader__.load({
  id: "dsh-cc-monitor",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    const React = require("react");
    const { createSnapshotStore } = require("@deepseek-ai/dsh-client-runtime/client");

    const NS = "cc-monitor";
    const inject = ["slots", "locale"];

    const zh = {
      "title": "cc-monitor",
      "description": "将 DeepSeek Harness 会话状态上报到 cc-monitor。",
      "enabled": "启用",
      "enabledHint": "关闭后停止向 cc-monitor 上报会话状态。",
      "serverUrl": "服务器 URL",
      "serverUrlHint": "cc-monitor 服务器的完整地址，例如 https://192.168.3.25:9876；留空则使用下方的主机和端口。",
      "parse": "解析",
      "host": "主机",
      "hostHint": "cc-monitor 服务器所在主机，默认 127.0.0.1。",
      "port": "端口",
      "portHint": "cc-monitor 服务端口，默认 9876。",
      "uid": "安装标识",
      "uidHint": "用于在 cc-monitor 中区分不同的 DSH 实例，格式如 dsh-xxxxxxxx-xxxx-...。",
      "installTitle": "安装 cc-monitor 服务器",
      "installHint": "在服务器上执行以下命令，通过 Docker 启动 cc-monitor。",
      "copy": "复制",
      "copied": "已复制",
      "save": "保存",
      "saving": "保存中…",
      "discard": "放弃",
      "loadFailed": "读取配置失败。",
      "expand": "展开设置",
      "collapse": "收起设置"
    };

    const en = {
      "title": "cc-monitor",
      "description": "Report DeepSeek Harness session activity to cc-monitor.",
      "enabled": "Enabled",
      "enabledHint": "When off, DSH session events are not reported.",
      "serverUrl": "Server URL",
      "serverUrlHint": "Full cc-monitor base URL, e.g. https://192.168.3.25:9876; leave blank to use the host and port below.",
      "parse": "Parse",
      "host": "Host",
      "hostHint": "cc-monitor host, defaults to 127.0.0.1.",
      "port": "Port",
      "portHint": "cc-monitor port, defaults to 9876.",
      "uid": "Installation UID",
      "uidHint": "Identifies this DSH instance in cc-monitor, e.g. dsh-xxxxxxxx-xxxx-....",
      "installTitle": "Install cc-monitor server",
      "installHint": "Run this on the server to start cc-monitor with Docker.",
      "copy": "Copy",
      "copied": "Copied",
      "save": "Save",
      "saving": "Saving…",
      "discard": "Discard",
      "loadFailed": "Failed to load configuration.",
      "expand": "Show settings",
      "collapse": "Hide settings"
    };

    class Controller {
      constructor() {
        this.store = createSnapshotStore({ status: "loading", value: null });
        this.load();
      }
      async load() {
        try {
          const resp = await fetch("/api/dsh-cc-monitor/config", { headers: { accept: "application/json" } });
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          const value = await resp.json();
          this.store.set({ status: "ready", value });
        } catch (err) {
          this.store.set({ status: "error", value: null, error: err?.message || String(err) });
        }
      }
      async save(patch) {
        this.store.set({ status: "saving", value: this.store.getSnapshot().value });
        try {
          const resp = await fetch("/api/dsh-cc-monitor/config", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(patch),
          });
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          const value = await resp.json();
          this.store.set({ status: "ready", value });
        } catch (err) {
          this.store.set({ status: "error", value: this.store.getSnapshot().value, error: err?.message || String(err) });
        }
      }
      inject() {
        return { hooks: { ccMonitorSettings: this.store }, save: (patch) => this.save(patch), reload: () => this.load() };
      }
    }

    function fallbackCopy(text) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try { document.execCommand("copy"); } catch (_) {}
      document.body.removeChild(ta);
    }

    function copyText(text) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
      } else {
        fallbackCopy(text);
      }
    }

    const INSTALL_COMMAND = [
      "mkdir cc-monitor && cd cc-monitor",
      "curl -O https://raw.githubusercontent.com/BolunHan/cc-monitor/main/docker-compose.yaml",
      "docker compose up -d"
    ].join("\n");

    const rowStyle = { display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", padding: "10px 0" };
    const labelStyle = { fontSize: "13px", fontWeight: "500", minWidth: "0" };
    const hintStyle = { fontSize: "12px", color: "var(--dsw-alias-label-tertiary, #666)", marginTop: "3px", lineHeight: "1.4" };
    const inputStyle = { boxSizing: "border-box", height: "32px", padding: "0 10px", borderRadius: "6px", border: "1px solid var(--dsw-alias-border-l2, #333)", background: "var(--dsw-alias-bg-layer-3, #fff)", color: "var(--dsw-alias-label-primary, #111)", width: "100%", maxWidth: "100%" };
    const buttonStyle = { boxSizing: "border-box", padding: "6px 12px", borderRadius: "6px", border: "1px solid var(--dsw-alias-border-l2, #333)", background: "transparent", color: "var(--dsw-alias-label-primary, #111)", cursor: "pointer", whiteSpace: "nowrap" };
    const codeStyle = { display: "block", whiteSpace: "pre-wrap", fontFamily: "SF Mono, Fira Code, monospace", fontSize: "12px", lineHeight: "1.5", padding: "10px", borderRadius: "6px", border: "1px solid var(--dsw-alias-border-l2, #333)", background: "var(--dsw-alias-bg-layer-3, #fff)", color: "var(--dsw-alias-label-primary, #111)", maxWidth: "100%", overflow: "auto" };

    function Toggle({ checked, disabled, onChange, label }) {
      return React.createElement("button", {
        type: "button",
        role: "switch",
        "aria-checked": checked ? "true" : "false",
        "aria-label": label,
        disabled,
        onClick: () => onChange(!checked),
        style: {
          position: "relative",
          width: "38px",
          height: "22px",
          borderRadius: "999px",
          border: "none",
          cursor: disabled ? "default" : "pointer",
          background: checked ? "var(--dsw-alias-brand-primary, #4d6bfe)" : "var(--dsw-alias-border-l2, #555)",
          opacity: disabled ? 0.5 : 1,
          padding: 0,
          flexShrink: 0
        }
      },
        React.createElement("span", { style: {
          position: "absolute",
          top: "3px",
          left: checked ? "19px" : "3px",
          width: "16px",
          height: "16px",
          borderRadius: "50%",
          background: "#fff",
          transition: "left 0.15s ease",
          display: "block"
        } })
      );
    }

    function Card(props) {
      const t = props.t;
      const snapshot = props.useCcMonitorSettings((s) => s);
      const [draft, setDraft] = React.useState(null);
      const [expanded, setExpanded] = React.useState(false);
      const [copied, setCopied] = React.useState(false);
      const [toast, setToast] = React.useState(false);

      React.useEffect(() => {
        if (snapshot.status === "ready" && snapshot.value) {
          setDraft({ ...snapshot.value });
        }
      }, [snapshot.status, snapshot.value]);

      if (snapshot.status === "loading") {
        return React.createElement("div", { style: { padding: "12px" } }, t("description"));
      }
      if (snapshot.status === "error" || !draft) {
        return React.createElement("div", { style: { padding: "12px", color: "var(--dsw-alias-label-error, #c00)" } }, t("loadFailed"));
      }

      const set = (key, value) => setDraft((d) => ({ ...d, [key]: value }));
      const onSave = async () => {
        await props.save(draft);
        setToast(true);
        setTimeout(() => setToast(false), 2200);
      };
      const onDiscard = () => setDraft({ ...snapshot.value });
      const copyInstall = () => { copyText(INSTALL_COMMAND); setCopied(true); setTimeout(() => setCopied(false), 1500); };
      const parseServerUrl = () => {
        const text = String(draft.serverUrl || "").trim();
        if (!text) return;
        let base = text;
        if (!/^https?:\/\//i.test(base)) base = "http://" + base;
        try {
          const url = new URL(base);
          set("host", url.hostname || "127.0.0.1");
          set("port", url.port || "9876");
        } catch (_) {}
      };

      return React.createElement("div", { style: { boxSizing: "border-box", maxWidth: "100%", overflow: "hidden", border: "1px solid var(--dsw-alias-border-l2, #333)", borderRadius: "12px", background: "var(--dsw-alias-bg-layer-3, transparent)", padding: "12px" } },
        React.createElement("button", { type: "button", onClick: () => setExpanded((v) => !v), style: { width: "100%", background: "transparent", border: "none", color: "inherit", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", padding: "4px 0" } },
          React.createElement("span", { style: { fontSize: "15px", fontWeight: "600" } }, t("title")),
          React.createElement("span", { style: { fontSize: "11px", color: "var(--dsw-alias-label-tertiary, #666)" } }, expanded ? t("collapse") : t("expand"))
        ),
        React.createElement("div", { style: { fontSize: "12px", color: "var(--dsw-alias-label-tertiary, #666)", marginTop: "4px" } }, t("description")),
        expanded ? React.createElement("div", { style: { marginTop: "10px", borderTop: "1px solid var(--dsw-alias-border-l2, #333)", paddingTop: "4px" } },
          React.createElement("div", { style: rowStyle },
            React.createElement("div", { style: { minWidth: 0 } },
              React.createElement("div", { style: labelStyle }, t("enabled")),
              React.createElement("div", { style: hintStyle }, t("enabledHint"))
            ),
            React.createElement(Toggle, { checked: !!draft.enabled, disabled: false, onChange: (v) => set("enabled", v), label: t("enabled") })
          ),
          React.createElement("div", { style: { padding: "10px 0" } },
            React.createElement("div", { style: labelStyle }, t("serverUrl")),
            React.createElement("div", { style: { display: "flex", gap: "8px", alignItems: "center", maxWidth: "100%" } },
              React.createElement("input", { value: draft.serverUrl ?? "", style: inputStyle, onChange: (e) => set("serverUrl", e.target.value) }),
              React.createElement("button", { style: buttonStyle, onClick: parseServerUrl }, t("parse"))
            ),
            React.createElement("div", { style: hintStyle }, t("serverUrlHint"))
          ),
          ["host", "port", "uid"].map((field) => {
            return React.createElement("div", { key: field, style: { padding: "10px 0" } },
              React.createElement("div", { style: labelStyle }, t(field)),
              React.createElement("input", { value: draft[field] ?? "", style: inputStyle, onChange: (e) => set(field, e.target.value) }),
              React.createElement("div", { style: hintStyle }, t(field + "Hint"))
            );
          }),
          React.createElement("div", { style: { padding: "10px 0" } },
            React.createElement("div", { style: labelStyle }, t("installTitle")),
            React.createElement("div", { style: hintStyle }, t("installHint")),
            React.createElement("code", { style: codeStyle }, INSTALL_COMMAND),
            React.createElement("div", { style: { display: "flex", justifyContent: "flex-end", marginTop: "8px" } },
              React.createElement("button", { style: buttonStyle, onClick: copyInstall }, copied ? t("copied") : t("copy"))
            )
          ),
          React.createElement("div", { style: { display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "8px" } },
            React.createElement("button", { style: buttonStyle, onClick: onDiscard }, t("discard")),
            React.createElement("button", { style: buttonStyle, onClick: onSave }, snapshot.status === "saving" ? t("saving") : t("save"))
          ),
          toast ? React.createElement("div", { style: { position: "fixed", bottom: "24px", right: "24px", zIndex: 9999, padding: "10px 14px", borderRadius: "8px", background: "var(--dsw-alias-bg-layer-3, #1a1d27)", color: "var(--dsw-alias-label-primary, #e1e4ed)", border: "1px solid var(--dsw-alias-border-l2, #333)", boxShadow: "0 8px 24px rgba(0,0,0,0.35)" } }, "[cc-monitor] Config Saved!") : null
        ) : null
      );
    }

    function apply(ctx) {
      ctx.effect(() => ctx.locale.register(NS, { zh, en }), "cc-monitor: dictionaries");
      const controller = new Controller();
      ctx.slots.inject("settings.plugin.item", () => ctx.slots.register({
        name: "settings.plugin.item",
        id: "cc-monitor",
        order: 100,
        locale: NS,
        inject: () => controller.inject()
      }, Card));
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  }
});
