# Latest Task Title for Codex

[中文](#中文说明) · [English](#english)

A small, open-source Codex plugin that keeps a task's sidebar title aligned
with the latest user request instead of leaving it anchored to the first
prompt.

> Status: early preview (`0.1.0`). It targets local tasks in the ChatGPT/Codex
> desktop app and depends on the host-provided `set_thread_title` tool.

## 中文说明

Codex 默认经常使用第一次提问作为任务标题。长对话改变方向后，左侧栏标题可能已经无法反映当前工作。这个插件会在每次根任务收到新问题时，请当前模型生成安全、简短的最新意图摘要，并通过 Codex 支持的标题接口更新侧边栏。

它不会直接修改 SQLite、rollout 或 session index，也不会在插件日志中保存原始问题。

## 安装

需要安装了插件功能的最新 ChatGPT/Codex 桌面版，以及 Python 3。

```sh
codex plugin marketplace add Deep-Octopus/codex-latest-task-title
codex plugin add latest-task-title@deep-octopus-plugins
```

然后：

1. 重启 ChatGPT/Codex 桌面应用。
2. 打开 `/hooks`。
3. 找到 `latest-task-title@deep-octopus-plugins` 的 `UserPromptSubmit` Hook。
4. 检查将要执行的 Python 命令并选择 **Trust**。
5. 新建一个 Codex 任务进行测试。

Hook 必须由用户亲自信任；这是 Codex 的安全机制。未信任时插件已经安装，但不会执行。

## 使用

安装并信任后不需要命令。正常对话即可：

- 第一次提问后生成简短标题。
- 后续提问会按照最新意图更新标题。
- “继续”“修一下这个”等指代性问题会结合附近对话，而不是直接成为标题。
- 子代理消息不会改写根任务标题。
- 现有旧任务不会批量回填；在它们下一次收到用户消息时才会更新。

如果你手动设置了标题，它也会在下一次提问时被自动覆盖。需要固定标题时请停用或卸载插件。

## 更新与卸载

```sh
# 拉取 marketplace 的最新版本，再重新安装插件
codex plugin marketplace upgrade deep-octopus-plugins
codex plugin add latest-task-title@deep-octopus-plugins

# 卸载插件
codex plugin remove latest-task-title@deep-octopus-plugins

# 不再使用该 marketplace 时移除它
codex plugin marketplace remove deep-octopus-plugins
```

更新后请重启桌面应用并使用新任务测试。

## English

Codex often derives a task name from the first prompt. When a long-running
conversation changes direction, that title can become stale. This plugin runs
on each root `UserPromptSubmit`, asks the model already handling the turn for a
safe summary of the newest intent, and updates the sidebar through Codex's
supported thread-title tool.

### Install

You need a current ChatGPT/Codex desktop build with plugin support and Python 3.

```sh
codex plugin marketplace add Deep-Octopus/codex-latest-task-title
codex plugin add latest-task-title@deep-octopus-plugins
```

Restart the desktop app, open `/hooks`, inspect the plugin's
`UserPromptSubmit` command, choose **Trust**, and test it in a new Codex task.
Hooks never run until the user explicitly trusts them.

After that, there is nothing to invoke: use Codex normally and the current root
task will be retitled after each user prompt. Existing tasks update on their
next prompt; this plugin does not perform a bulk historical rename.

## How it works

1. A plugin-bundled `UserPromptSubmit` hook runs whenever a root user prompt is
   submitted.
2. The hook adds a short, high-priority housekeeping instruction to that model
   turn. It never stores or repeats the prompt.
3. The model summarizes the newest intent and calls Codex's official
   `set_thread_title` host tool once.
4. Codex persists the rename through its supported thread-name path, so the
   sidebar updates without editing SQLite or session files directly.

The generated title stays in the user's language, is capped at 48 Unicode
characters, and must exclude credentials, tokens, URLs, paths, and personal
data. Context-dependent prompts such as “继续” are titled using the actual topic
of the follow-up rather than that literal word.

## Safety and scope

- Root Codex tasks only; subagent prompts are ignored.
- Local Codex Desktop tasks are the primary supported surface.
- The hook silently skips ChatGPT tasks, remote tasks, or hosts that do not
  expose `set_thread_title`.
- No database, rollout, or session-index file is modified directly.
- No prompt or title is logged by the plugin.
- A manually chosen title will be replaced on the next user prompt by design.
  Disable the plugin when a task title should remain fixed.

## Limitations

- The model must follow the injected housekeeping instruction and the host must
  expose `set_thread_title`; unsupported task surfaces are skipped silently.
- A title update uses a small amount of the current turn's context and one host
  tool call. It does not make a separate OpenAI API request.
- Manual titles are overwritten on the next user prompt by design.
- The plugin does not retroactively rename every historical task.

## Privacy and security

- The hook reads Codex's standard `UserPromptSubmit` JSON from stdin only.
- It does not log, persist, or echo the prompt.
- The prompt text is deliberately not copied into the injected instruction.
- Titles are instructed to exclude passwords, tokens, credentials, URLs,
  paths, personal data, and other secrets.
- It modifies no Codex database or session file directly.
- Subagent prompts are ignored because subagents can share the root session id.

You should still inspect the short Python source before trusting the hook.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/latest-task-title
```

You can also exercise the hook without a Codex session:

```sh
printf '%s' '{"hook_event_name":"UserPromptSubmit","session_id":"demo","prompt":"fix the upload retry"}' \
  | python3 plugins/latest-task-title/scripts/latest_task_title.py
```

The repository root is a Codex marketplace; the installable plugin lives at
`plugins/latest-task-title/`.

## License

[MIT](LICENSE)
