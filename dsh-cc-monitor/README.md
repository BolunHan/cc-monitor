# dsh-cc-monitor

A host-side [DSH](https://github.com/deepseek-ai/deepseek-harness) plugin that
reports session activity to a [cc-monitor](https://github.com/BolunHan/cc-monitor)
server. It maps DSH session events to the same normalized hook payloads the
server already accepts, then POSTs them to `/api/event` with `agent: dsh`.

## Install

```bash
dsh plugin --profile web add link:/path/to/cc-monitor/dsh-cc-monitor
```

Then make sure the profile's `package.json` lists `dsh-cc-monitor` in
`dsh.profile.bundles` (the `dsh plugin add` command normally handles this for
out-of-tree bundles; verify with `dsh --profile web --dump-config`).

## Configuration

Defaults are designed for a local cc-monitor server on `127.0.0.1:9876`.
Override them with environment variables or a patch entry:

```yaml
- insert:
    - id: cc-monitor
      name: 'dsh-cc-monitor'
      config:
        # Full override; host/port below are ignored when this is set.
        serverUrl: 'https://192.168.3.25:9876'
        # Or configure host + port separately:
        # host: '192.168.3.25'
        # port: 9876
        uid: 'my-dsh-instance'
```

If `serverUrl` is set, `port` overrides its port. If `serverUrl` is omitted,
`host` + `port` are used to build `http://<host>:<port>`.

| Setting      | Environment        | Default                  |
| ------------ | ------------------ | ------------------------ |
| `serverUrl`  | `CC_MONITOR_URL`   | —                        |
| `host`       | `CC_MONITOR_HOST`  | `127.0.0.1`              |
| `port`       | `CC_MONITOR_PORT`  | `9876`                   |
| `uid`        | `CC_MONITOR_UID`   | `dsh-default`            |
| `enabled`    | —                  | `true`                   |

## How it maps

| DSH event          | cc-monitor event      | State             |
| ------------------ | --------------------- | ----------------- |
| direct `user/message` | `UserPromptSubmit` | working           |
| `assistant/message` | `Stop`              | pending_review    |
| `tool/call`        | `PreToolUse`          | working           |
| approval tool call | `PermissionRequest`   | pending_approval  |
| `tool/result`      | `PostToolUse`         | working           |
| `session/disposed` | `SessionEnd`          | all_done          |

