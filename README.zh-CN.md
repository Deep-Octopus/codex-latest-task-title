# Codex 最新任务标题插件

**语言：** 中文 · [英文](README.md)

根据最近一次提问自动更新左侧栏任务标题。手动修改标题后，该任务会永久停止自动更新，不再覆盖手动标题。

## 安装

需要支持插件功能的 Codex 桌面版和 Python 3.10 或更高版本。

```sh
codex plugin marketplace add Deep-Octopus/codex-latest-task-title
codex plugin add latest-task-title@deep-octopus-plugins
```

重启应用，打开 `/hooks`，找到本插件的两个钩子并选择信任。然后新建任务测试。

## 使用

安装后正常对话即可。插件会：

- 根据最新问题更新根任务标题；
- 结合上下文理解“继续”“修一下”等提问；
- 忽略子代理消息；
- 检测手动改名，并永久锁定该任务标题。

插件只读检查当前标题，只保存自动标题的哈希，不保存问题或明文标题，也不直接修改数据库。

## 更新与卸载

```sh
codex plugin marketplace upgrade deep-octopus-plugins
codex plugin add latest-task-title@deep-octopus-plugins

codex plugin remove latest-task-title@deep-octopus-plugins
```

更新后请重启应用，并新建任务测试。

## 开发

```sh
python3 -m unittest discover -s plugins/latest-task-title/tests -v
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/latest-task-title
```

采用 [MIT 许可证](LICENSE)。
