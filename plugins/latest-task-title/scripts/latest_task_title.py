#!/usr/bin/env python3
"""Refresh Codex task titles while preserving manually chosen titles.

The hook never stores prompts or plain-text titles. It reads Codex's local
thread metadata in read-only mode and stores only a SHA-256 digest of the last
automatic title. If the visible title later differs, the task is permanently
locked and future prompts no longer receive a rename instruction.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_HOOK_INPUT_BYTES = 16 * 1024 * 1024
STATE_VERSION = 1
STATE_DIRECTORY_NAME = "latest-task-title"


@dataclass(frozen=True)
class TitleSnapshot:
    """The current visible title and Codex's original first-user-message title."""

    current: str
    initial: str


def _normalized_title(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _title_digest(title: str) -> str:
    return hashlib.sha256(_normalized_title(title).encode("utf-8")).hexdigest()


def _session_key(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def _codex_home(payload: dict[str, Any] | None = None) -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()

    transcript_path = (payload or {}).get("transcript_path")
    if isinstance(transcript_path, str) and transcript_path:
        transcript = Path(transcript_path).expanduser()
        for parent in transcript.parents:
            if parent.name in {"sessions", "archived_sessions"}:
                return parent.parent

    return Path.home() / ".codex"


def _state_directory(
    payload: dict[str, Any] | None = None,
    override: Path | None = None,
) -> Path:
    return override if override is not None else _codex_home(payload) / STATE_DIRECTORY_NAME


def _state_path(
    session_id: str,
    payload: dict[str, Any] | None = None,
    state_dir: Path | None = None,
) -> Path:
    return _state_directory(payload, state_dir) / f"{_session_key(session_id)}.json"


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": STATE_VERSION}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        # A damaged state file must fail closed so a manual title is not lost.
        return {"version": STATE_VERSION, "locked": True, "lock_reason": "invalid_state"}

    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        return {"version": STATE_VERSION, "locked": True, "lock_reason": "invalid_state"}
    return data


def _save_state(path: Path, state: dict[str, Any]) -> bool:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(state, temporary, ensure_ascii=True, separators=(",", ":"))
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
        return True
    except OSError:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return False


def _sqlite_path(payload: dict[str, Any], override: Path | None = None) -> Path | None:
    if override is not None:
        return override

    sqlite_home = os.environ.get("CODEX_SQLITE_HOME")
    candidates = []
    if sqlite_home:
        candidates.append(Path(sqlite_home).expanduser() / "state_5.sqlite")

    codex_home = _codex_home(payload)
    candidates.extend(
        [
            codex_home / "state_5.sqlite",
            codex_home / "sqlite" / "state_5.sqlite",
        ]
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _read_title_snapshot(
    payload: dict[str, Any],
    session_id: str,
    db_path: Path | None = None,
) -> tuple[bool, TitleSnapshot | None]:
    """Return (database_available, snapshot).

    A missing row is a normal first-turn condition and returns (True, None).
    The connection is URI read-only and never mutates Codex state.
    """

    resolved_db_path = _sqlite_path(payload, db_path)
    if resolved_db_path is None or not resolved_db_path.is_file():
        return False, None

    try:
        uri = f"{resolved_db_path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=0.25)) as connection:
            connection.execute("PRAGMA query_only = ON")
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(threads)")
            }
            if "title" not in columns:
                return False, None

            selected = ["title"]
            selected.append("name" if "name" in columns else "NULL AS name")
            selected.append(
                "first_user_message"
                if "first_user_message" in columns
                else "NULL AS first_user_message"
            )
            selected.append(
                "history_mode" if "history_mode" in columns else "'legacy' AS history_mode"
            )
            row = connection.execute(
                f"SELECT {', '.join(selected)} FROM threads WHERE id = ?",  # noqa: S608
                (session_id,),
            ).fetchone()
    except sqlite3.Error:
        return False, None

    if row is None:
        return True, None

    title, name, first_user_message, history_mode = row
    visible_title = name if history_mode != "legacy" and _normalized_title(name) else title
    return True, TitleSnapshot(
        current=_normalized_title(visible_title),
        initial=_normalized_title(first_user_message),
    )


def _is_root_task(payload: dict[str, Any]) -> bool:
    return payload.get("agent_id") in (None, "")


def _lock_state(path: Path, state: dict[str, Any], reason: str) -> None:
    state.pop("pending_turn_id", None)
    state["locked"] = True
    state["lock_reason"] = reason
    _save_state(path, state)


def _build_title_instruction(session_id: str) -> dict[str, Any]:
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


def _handle_user_prompt(
    payload: dict[str, Any],
    session_id: str,
    state_dir: Path | None,
    db_path: Path | None,
) -> dict[str, Any] | None:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return None

    state_path = _state_path(session_id, payload, state_dir)
    state = _load_state(state_path)
    if state.get("locked") is True:
        return None

    database_available, snapshot = _read_title_snapshot(payload, session_id, db_path)
    if not database_available:
        # Fail closed: without the current title, manual-title protection cannot
        # be guaranteed.
        return None

    previous_digest = state.get("last_automatic_title_sha256")
    if isinstance(previous_digest, str):
        if snapshot is None or _title_digest(snapshot.current) != previous_digest:
            _lock_state(state_path, state, "title_changed")
            return None
    elif snapshot is not None and snapshot.current:
        # On first use, an existing title that differs from Codex's original
        # first-message title may be manual. Preserve it instead of guessing.
        if not snapshot.initial or snapshot.current != snapshot.initial:
            _lock_state(state_path, state, "preexisting_custom_title")
            return None

    turn_id = payload.get("turn_id")
    state["pending_turn_id"] = turn_id if isinstance(turn_id, str) else ""
    state.pop("lock_reason", None)
    if not _save_state(state_path, state):
        return None

    return _build_title_instruction(session_id)


def _handle_stop(
    payload: dict[str, Any],
    session_id: str,
    state_dir: Path | None,
    db_path: Path | None,
) -> None:
    state_path = _state_path(session_id, payload, state_dir)
    state = _load_state(state_path)
    if state.get("locked") is True or "pending_turn_id" not in state:
        return

    pending_turn_id = state.get("pending_turn_id")
    turn_id = payload.get("turn_id")
    if pending_turn_id and isinstance(turn_id, str) and pending_turn_id != turn_id:
        return

    database_available, snapshot = _read_title_snapshot(payload, session_id, db_path)
    if not database_available or snapshot is None or not snapshot.current:
        return

    state["last_automatic_title_sha256"] = _title_digest(snapshot.current)
    state.pop("pending_turn_id", None)
    _save_state(state_path, state)


def build_hook_output(
    payload: dict[str, Any],
    *,
    state_dir: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Handle supported hook events for a root task, or return None to skip."""
    if not _is_root_task(payload):
        return None

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None

    event_name = payload.get("hook_event_name")
    if event_name == "UserPromptSubmit":
        return _handle_user_prompt(payload, session_id, state_dir, db_path)
    if event_name == "Stop":
        _handle_stop(payload, session_id, state_dir, db_path)
    return None


def _unlock_session(session_id: str) -> int:
    if not session_id.strip():
        return 2
    path = _state_path(session_id)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return 1
    return 0


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--unlock":
        return _unlock_session(sys.argv[2])
    if len(sys.argv) != 1:
        return 2

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
