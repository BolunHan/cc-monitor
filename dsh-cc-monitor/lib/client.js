window.__ModuleLoader__.load({
  id: "dsh-cc-monitor",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    const React = require("react");
    const { createSnapshotStore } = require("@deepseek-ai/dsh-client-runtime/client");

    const NS = "cc-monitor";
    const CC_MONITOR_NS = "cc-monitor";
    const inject = ["slots", "locale", "connection", "settingsScope", "remote"];

    const zh = {
      "settings.title": "cc-monitor 上报",
      "settings.description": "DeepSeek Harness 会话状态上报参数。",
      "settings.enabled": "启用 cc-monitor",
      "settings.enabledHint": "关闭后停止向 cc-monitor 上报会话状态。",
      "settings.serverUrl": "服务器 URL",
      "settings.serverUrlHint": "完整地址，例如 https://192.168.3.25:9876；留空则使用 host + port。",
      "settings.host": "服务器主机",
      "settings.hostHint": "cc-monitor 服务器地址，默认 127.0.0.1。",
      "settings.port": "服务器端口",
      "settings.portHint": "cc-monitor 端口，默认 9876。",
      "settings.uid": "安装标识",
      "settings.uidHint": "发送到 cc-monitor 的 cc_monitor_uid。",
      "settings.overridden": "已覆盖",
      "settings.reset": "恢复默认",
      "settings.notExposed": "当前 DSH 版本未向设置页暴露本插件的配置命名空间，表单不可用。可编辑 ~/.dsh/settings.yaml 直接配置，或为 dsh-host-apiproxy 的 WEB_SETTINGS_NAMESPACES 白名单补充本命名空间后重启。",
      "settings.readOnly": "当前部署的设置只读。",
      "settings.inherit": "继承",
      "settings.on": "开",
      "settings.off": "关",
      "settings.expand": "展开设置",
      "settings.collapse": "收起设置",
      "settings.save": "保存",
      "settings.saving": "保存中…",
      "settings.discard": "放弃",
      "settings.unsaved": "未保存",
      "settings.saveFailed": "部署未接受这些值，已保留供你修改。",
      "settings.invalidNumber": "请输入数字，留空则使用默认值。"
    };

    const en = {
      "settings.title": "cc-monitor reporting",
      "settings.description": "Report DSH session activity to a cc-monitor server.",
      "settings.enabled": "Enable cc-monitor",
      "settings.enabledHint": "When off, DSH session events are not reported.",
      "settings.serverUrl": "Server URL",
      "settings.serverUrlHint": "Full base URL, e.g. https://192.168.3.25:9876; blank uses host + port.",
      "settings.host": "Server host",
      "settings.hostHint": "cc-monitor host, defaults to 127.0.0.1.",
      "settings.port": "Server port",
      "settings.portHint": "cc-monitor port, defaults to 9876.",
      "settings.uid": "Installation UID",
      "settings.uidHint": "cc_monitor_uid sent to cc-monitor.",
      "settings.overridden": "Overridden",
      "settings.reset": "Reset to default",
      "settings.notExposed": "This DSH version does not expose this plugin's settings namespace to the configuration page, so the form is unavailable. Edit ~/.dsh/settings.yaml directly, or add the namespace to dsh-host-apiproxy's WEB_SETTINGS_NAMESPACES allowlist and restart.",
      "settings.readOnly": "This deployment stores settings read-only.",
      "settings.inherit": "Inherit",
      "settings.on": "On",
      "settings.off": "Off",
      "settings.expand": "Show settings",
      "settings.collapse": "Hide settings",
      "settings.save": "Save",
      "settings.saving": "Saving…",
      "settings.discard": "Discard",
      "settings.unsaved": "Unsaved",
      "settings.saveFailed": "The deployment did not accept these values; they were left for you to correct.",
      "settings.invalidNumber": "Enter a number, or leave blank to use the default."
    };

    function stringSpec(field) {
      return {
        field,
        format: (value) => typeof value === "string" ? value : "",
        parse: (text) => {
          const trimmed = String(text).trim();
          if (trimmed === "") return { kind: "clear" };
          return { kind: "set", value: trimmed };
        }
      };
    }

    function numberSpec(field) {
      return {
        field,
        format: (value) => typeof value === "number" ? String(value) : "",
        parse: (text) => {
          const trimmed = String(text).trim();
          if (trimmed === "") return { kind: "clear" };
          const parsed = Number(trimmed);
          if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 1 || parsed > 65535) return undefined;
          return { kind: "set", value: parsed };
        }
      };
    }

    function booleanSpec(field) {
      return {
        field,
        format: (value) => typeof value === "boolean" ? String(value) : "",
        parse: (text) => {
          const trimmed = String(text).trim();
          if (trimmed === "") return { kind: "clear" };
          if (trimmed === "true") return { kind: "set", value: true };
          if (trimmed === "false") return { kind: "set", value: false };
          return undefined;
        }
      };
    }

    const SPECS = {
      enabled: booleanSpec("enabled"),
      serverUrl: stringSpec("serverUrl"),
      host: stringSpec("host"),
      port: numberSpec("port"),
      uid: stringSpec("uid")
    };

    class Controller {
      constructor(scope) {
        this.scope = scope;
        this.staged = new Map();
        this.saving = false;
        this.failed = false;
        this.failedReason = undefined;
        this.store = createSnapshotStore(this.snapshot());
        scope.subscribe(() => this.publish());
      }

      snapshot() {
        const snap = this.scope.getSnapshot();
        const plan = this.plan();
        return {
          available: snap.status !== "loading",
          exposed: snap.status === "ready",
          writable: snap.writable,
          dirty: this.staged.size > 0,
          invalid: plan.some((item) => item.invalid),
          saving: this.saving,
          failed: this.failed,
          ...(this.failedReason === undefined ? {} : { failedReason: this.failedReason }),
          enabled: this.field("enabled"),
          serverUrl: this.field("serverUrl"),
          host: this.field("host"),
          port: this.field("port"),
          uid: this.field("uid")
        };
      }

      sectionValue(field) {
        return this.scope.getSnapshot().value?.[field];
      }

      userLayer() {
        return this.scope.getSnapshot().user;
      }

      stored(field) {
        const user = this.userLayer();
        return user !== undefined && Object.hasOwn(user, field);
      }

      field(field) {
        const spec = SPECS[field];
        const staged = this.staged.get(field);
        if (staged === undefined) {
          return {
            text: spec.format(this.sectionValue(field)),
            overridden: this.stored(field),
            invalid: false
          };
        }
        const write = staged.clear ? { kind: "clear" } : spec.parse(staged.text);
        return {
          text: staged.text,
          overridden: write?.kind === "set",
          invalid: write === undefined
        };
      }

      plan() {
        const items = [];
        for (const [field, staged] of this.staged) {
          const spec = SPECS[field];
          if (staged.clear) {
            items.push({ field, invalid: false, op: this.stored(field) ? "unset" : null });
            continue;
          }
          if (staged.text === spec.format(this.sectionValue(field))) {
            items.push({ field, invalid: false, op: null });
            continue;
          }
          const write = spec.parse(staged.text);
          if (write === undefined) {
            items.push({ field, invalid: true, op: null });
          } else if (write.kind === "set") {
            items.push({ field, invalid: false, op: "set", value: write.value });
          } else {
            items.push({ field, invalid: false, op: this.stored(field) ? "unset" : null });
          }
        }
        return items;
      }

      stage(field, edit) {
        this.staged.set(field, edit);
        this.failed = false;
        this.failedReason = undefined;
        this.publish();
      }

      async save() {
        const plan = this.plan();
        if (plan.length === 0 || this.saving || plan.some((item) => item.invalid)) return;
        this.saving = true;
        this.failed = false;
        this.failedReason = undefined;
        this.publish();
        let landed = 0;
        for (const item of plan) {
          if (item.op === "set") {
            await this.scope.set(item.field, item.value);
            if (this.scope.getSnapshot().user?.[item.field] === item.value) landed++;
          } else if (item.op === "unset") {
            await this.scope.unset(item.field);
            if (!this.stored(item.field)) landed++;
          }
        }
        this.saving = false;
        this.failed = landed !== plan.filter((item) => item.op !== null).length;
        for (const item of plan) {
          if (item.op !== null && ((item.op === "set" && this.scope.getSnapshot().user?.[item.field] === item.value) || (item.op === "unset" && !this.stored(item.field)))) {
            this.staged.delete(item.field);
          }
        }
        this.publish();
      }

      actions() {
        return {
          edit: (field, text) => this.stage(field, { text, clear: false }),
          resetField: (field) => this.stage(field, { text: SPECS[field].format(this.scope.getSnapshot().base?.[field]), clear: true }),
          save: () => this.save(),
          discard: () => {
            this.staged.clear();
            this.failed = false;
            this.failedReason = undefined;
            this.publish();
          }
        };
      }

      inject() {
        return { hooks: { ccMonitorSettings: this.store }, ...this.actions() };
      }

      publish() {
        this.store.set(this.snapshot());
      }
    }

    const fieldStyle = { display: "flex", flexDirection: "column", gap: "4px", padding: "8px 0" };
    const labelStyle = { fontSize: "13px", fontWeight: "500" };
    const inputStyle = { height: "32px", padding: "0 10px", borderRadius: "6px", border: "1px solid var(--dsw-alias-border-l2, #333)", background: "var(--dsw-alias-bg-layer-3, #fff)", color: "var(--dsw-alias-label-primary, #111)" };
    const buttonStyle = { padding: "6px 12px", borderRadius: "6px", border: "1px solid var(--dsw-alias-border-l2, #333)", background: "transparent", color: "var(--dsw-alias-label-primary, #111)", cursor: "pointer" };

    function Card(props) {
      const t = props.t;
      const state = props.useCcMonitorSettings((snapshot) => snapshot);
      const disabled = !state.writable;

      return React.createElement("div", { style: { padding: "12px 0" } },
        React.createElement("div", { style: { fontSize: "15px", fontWeight: "600", marginBottom: "4px" } }, t("settings.title")),
        React.createElement("div", { style: { fontSize: "12px", color: "var(--dsw-alias-label-tertiary, #666)", marginBottom: "8px" } }, t("settings.description")),
        React.createElement("label", { style: fieldStyle },
          React.createElement("span", { style: labelStyle }, t("settings.enabled")),
          React.createElement("input", { type: "checkbox", checked: state.enabled.text === "true", disabled, onChange: (e) => props.edit("enabled", String(e.target.checked)) })
        ),
        ["serverUrl", "host", "port", "uid"].map((field) => {
          const fieldState = state[field];
          return React.createElement("label", { key: field, style: fieldStyle },
            React.createElement("span", { style: labelStyle }, t("settings." + field)),
            React.createElement("input", { value: fieldState.text || "", disabled, style: inputStyle, onChange: (e) => props.edit(field, e.target.value) })
          );
        }),
        React.createElement("div", { style: { display: "flex", gap: "8px", justifyContent: "flex-end", marginTop: "8px" } },
          React.createElement("button", { disabled, style: buttonStyle, onClick: props.discard }, t("settings.discard")),
          React.createElement("button", { disabled, style: buttonStyle, onClick: props.save }, t("settings.save"))
        )
      );
    }

    function apply(ctx) {
      ctx.effect(() => ctx.locale.register(NS, { zh, en }), "cc-monitor: dictionaries");
      const binder = ctx.get("webUiSettings") ?? ctx.settingsScope;
      const controller = new Controller(binder.bind({ namespace: CC_MONITOR_NS }));
      ctx.slots.inject("web-ui.plugin.item", () => ctx.slots.register({
        name: "web-ui.plugin.item",
        id: "cc-monitor",
        order: 120,
        locale: NS,
        inject: () => controller.inject()
      }, Card));
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  }
});
