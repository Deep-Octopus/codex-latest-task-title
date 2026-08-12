# Latest Task Title for Codex

Updates the sidebar task title from the latest request. Once you rename a task manually, automatic updates stop permanently for that task.

## Install

Requires Codex Desktop with plugin support and Python 3.10 or newer.

```sh
codex plugin marketplace add Deep-Octopus/codex-latest-task-title
codex plugin add latest-task-title@deep-octopus-plugins
```

Restart the app, open `/hooks`, trust both plugin hooks, and test it in a new task.

## Use

Use Codex normally after installation. The plugin:

- updates root task titles from the latest request;
- uses nearby context for prompts such as “continue” or “fix that”;
- ignores subagent messages;
- permanently locks automatic updates after detecting a manual rename.

It reads the current title without modifying the database and stores only a hash of its last automatic title. Prompts and plain-text titles are never stored.

## Update or remove

```sh
codex plugin marketplace upgrade deep-octopus-plugins
codex plugin add latest-task-title@deep-octopus-plugins

codex plugin remove latest-task-title@deep-octopus-plugins
```

Restart the app and test the update in a new task.

## Development

```sh
python3 -m unittest discover -s plugins/latest-task-title/tests -v
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/latest-task-title
```

[MIT License](LICENSE).
