import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import state_manager


class StateManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_then_get_roundtrip(self):
        state_manager.add_task("task_1", "a cat", "model-x", {"k": 1}, state_file=self.state_file)
        task = state_manager.get_task("task_1", state_file=self.state_file)
        self.assertEqual(task["prompt"], "a cat")
        self.assertEqual(task["model"], "model-x")
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["metadata"], {"k": 1})

    def test_update_existing(self):
        state_manager.add_task("task_1", "p", "m", state_file=self.state_file)
        ok = state_manager.update_task("task_1", "completed", {"file": "x.mp4"}, state_file=self.state_file)
        self.assertTrue(ok)
        task = state_manager.get_task("task_1", state_file=self.state_file)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"], {"file": "x.mp4"})

    def test_update_missing_returns_false(self):
        self.assertFalse(state_manager.update_task("nope", "completed", state_file=self.state_file))

    def test_list_active_excludes_terminal(self):
        state_manager.add_task("t1", "p", "m", state_file=self.state_file)
        state_manager.add_task("t2", "p", "m", state_file=self.state_file)
        state_manager.add_task("t3", "p", "m", state_file=self.state_file)
        state_manager.update_task("t2", "completed", state_file=self.state_file)
        state_manager.update_task("t3", "failed", state_file=self.state_file)
        active = state_manager.list_active_tasks(state_file=self.state_file)
        self.assertEqual([tid for tid, _ in active], ["t1"])

    def test_corrupt_state_file_returns_empty(self):
        self.state_file.write_text("{not json")
        self.assertEqual(state_manager.load_state(self.state_file), {})


if __name__ == "__main__":
    unittest.main()
