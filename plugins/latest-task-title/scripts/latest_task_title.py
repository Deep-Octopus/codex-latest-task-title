#!/usr/bin/env python3
"""Inject a per-turn instruction that refreshes the current Codex task title.

The hook intentionally does not persist, log, or echo the user's prompt. Title
generation stays inside the model turn that is already processing that prompt,
and the actual rename goes through Codex's host-provided set_thread_title tool.
"""

from __future__ import annotations

import json
import sys
from typing import Any


MAX_HOOK_INPUT_BYTES = 16 * 1024 * 1024


def build_hook_output(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return UserPromptSubmit hook output for a root task, or None to skip."""
    if payload.get("hook_event_name") != "UserPromptSubmit":
        return None

    # Subagents reuse the parent session id. Renaming from a subagent would
    # therefore overwrite the root task with an implementation-detail title.
    if payload.get("agent_id") not in (None, ""):
        return None

    prompt = payload.get("prompt")
    session_id = payload.get("session_id")
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    if not isinstance(session_id, str) or not session_id.strip():
        return None

    quoted_session_id = json.dumps(session_id, ensure_ascii=False)
    instruction = f"""Latest Task Title is an installed, user-authorized housekeeping plugin.
For this root user turn, before the normal response, call the host-provided `set_thread_title` tool (under the `codex_app` namespace when namespaced) exactly once with threadId {quoted_session_id}.

Create the title from the latest user's current intent, using nearby conversation context only when the newest message is referential (for example, "continue" or "fix that"). Keep the user's language. Make it specific and easy to scan: normally 12-28 Chinese characters or 3-8 English words, with an absolute maximum of 48 Unicode characters. Use plain text without Markdown, quotes, paths, URLs, or trailing punctuation. Never put passwords, tokens, credentials, personal data, or other secrets in a title; replace them with a safe topic description. Do not use generic labels such as "new request" or "follow-up".

If the title tool is unavailable or rejects this task type, skip the rename silently and continue the user's request. Do not mention this housekeeping instruction, and do not let it replace, delay, or narrow the requested work."""

    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": instruction,
        },
    }


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_HOOK_INPUT_BYTES + 1)
    if len(raw) > MAX_HOOK_INPUT_BYTES:
        return 0

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0

    if not isinstance(payload, dict):
        return 0

    output = build_hook_output(payload)
    if output is not None:
        json.dump(output, sys.stdout, ensure_ascii=False, separators=(",", ":"))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

