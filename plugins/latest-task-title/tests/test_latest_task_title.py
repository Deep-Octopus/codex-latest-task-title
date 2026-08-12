from __future__ import annotations

import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "latest_task_title.py"
SPEC = importlib.util.spec_from_file_location("latest_task_title", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class HookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary_directory.name)
        self.state_dir = self.root / "state"
        self.db_path = self.root / "state_5.sqlite"
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    name TEXT,
                    first_user_message TEXT,
                    history_mode TEXT
                )"""
            )
            connection.commit()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _insert_thread(self, title: str, first_message: str = "First request") -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, NULL, ?, 'legacy')",
                ("thread-123", title, first_message),
            )
            connection.commit()

    def _set_title(self, title: str) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "UPDATE threads SET title = ? WHERE id = ?", (title, "thread-123")
            )
            connection.commit()

    def _payload(self, event: str, turn_id: str = "turn-1") -> dict[str, object]:
        return {
            "hook_event_name": event,
            "session_id": "thread-123",
            "turn_id": turn_id,
            "agent_id": None,
            "prompt": "Fix the upload retry",
        }

    def _run(self, payload: dict[str, object]):
        return MODULE.build_hook_output(
            payload,
            state_dir=self.state_dir,
            db_path=self.db_path,
        )

    def _state_contents(self) -> str:
        state_files = list(self.state_dir.glob("*.json"))
        self.assertEqual(len(state_files), 1)
        return state_files[0].read_text(encoding="utf-8")

    def test_root_prompt_requests_one_safe_title_update(self) -> None:
        self._insert_thread("First request")
        payload = self._payload("UserPromptSubmit")
        payload["prompt"] = "Deploy with password super-secret-123"

        output = self._run(payload)

        self.assertIsNotNone(output)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("set_thread_title", context)
        self.assertIn('threadId "thread-123"', context)
        self.assertIn("exactly once", context)
        self.assertNotIn("super-secret-123", context)

    def test_automatic_title_continues_updating(self) -> None:
        self._insert_thread("First request")
        self.assertIsNotNone(self._run(self._payload("UserPromptSubmit", "turn-1")))
        self._set_title("Fix upload retry")
        self.assertIsNone(self._run(self._payload("Stop", "turn-1")))

        output = self._run(self._payload("UserPromptSubmit", "turn-2"))

        self.assertIsNotNone(output)

    def test_manual_title_locks_task_permanently(self) -> None:
        self._insert_thread("First request")
        self.assertIsNotNone(self._run(self._payload("UserPromptSubmit", "turn-1")))
        self._set_title("Automatic title")
        self._run(self._payload("Stop", "turn-1"))

        self._set_title("My fixed title")
        self.assertIsNone(self._run(self._payload("UserPromptSubmit", "turn-2")))
        self._set_title("Automatic title")
        self.assertIsNone(self._run(self._payload("UserPromptSubmit", "turn-3")))

        state = json.loads(self._state_contents())
        self.assertTrue(state["locked"])
        self.assertEqual(state["lock_reason"], "title_changed")

    def test_preexisting_custom_title_is_preserved(self) -> None:
        self._insert_thread("My manual title", first_message="First request")

        self.assertIsNone(self._run(self._payload("UserPromptSubmit")))

        state = json.loads(self._state_contents())
        self.assertTrue(state["locked"])
        self.assertEqual(state["lock_reason"], "preexisting_custom_title")

    def test_state_never_contains_plain_text_title_or_prompt(self) -> None:
        self._insert_thread("First request")
        self._run(self._payload("UserPromptSubmit", "turn-1"))
        self._set_title("Private automatic title")
        self._run(self._payload("Stop", "turn-1"))

        contents = self._state_contents()
        self.assertNotIn("Private automatic title", contents)
        self.assertNotIn("Fix the upload retry", contents)
        self.assertIn("last_automatic_title_sha256", contents)

    def test_subagent_prompt_is_ignored(self) -> None:
        self._insert_thread("First request")
        payload = self._payload("UserPromptSubmit")
        payload["agent_id"] = "agent-456"
        self.assertIsNone(self._run(payload))

    def test_empty_prompt_is_ignored(self) -> None:
        self._insert_thread("First request")
        payload = self._payload("UserPromptSubmit")
        payload["prompt"] = "   "
        self.assertIsNone(self._run(payload))

    def test_missing_database_fails_closed(self) -> None:
        self.db_path.unlink()
        self.assertIsNone(self._run(self._payload("UserPromptSubmit")))

    def test_unrelated_event_is_ignored(self) -> None:
        self._insert_thread("First request")
        self.assertIsNone(self._run(self._payload("SessionStart")))


if __name__ == "__main__":
    unittest.main()
