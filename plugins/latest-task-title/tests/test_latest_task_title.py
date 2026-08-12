from __future__ import annotations

import importlib.util
import pathlib
import unittest


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "latest_task_title.py"
)
SPEC = importlib.util.spec_from_file_location("latest_task_title", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BuildHookOutputTests(unittest.TestCase):
    def test_root_prompt_requests_one_safe_title_update(self) -> None:
        secret_prompt = "Deploy with password super-secret-123"
        output = MODULE.build_hook_output(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "thread-123",
                "agent_id": None,
                "prompt": secret_prompt,
            }
        )

        self.assertIsNotNone(output)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("set_thread_title", context)
        self.assertIn('threadId "thread-123"', context)
        self.assertIn("exactly once", context)
        self.assertNotIn("super-secret-123", context)

    def test_subagent_prompt_is_ignored(self) -> None:
        output = MODULE.build_hook_output(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "thread-123",
                "agent_id": "agent-456",
                "prompt": "Inspect the parser",
            }
        )
        self.assertIsNone(output)

    def test_empty_prompt_is_ignored(self) -> None:
        output = MODULE.build_hook_output(
            {
                "hook_event_name": "UserPromptSubmit",
                "session_id": "thread-123",
                "prompt": "   ",
            }
        )
        self.assertIsNone(output)

    def test_unrelated_event_is_ignored(self) -> None:
        output = MODULE.build_hook_output(
            {
                "hook_event_name": "SessionStart",
                "session_id": "thread-123",
                "prompt": "Inspect the parser",
            }
        )
        self.assertIsNone(output)


if __name__ == "__main__":
    unittest.main()

