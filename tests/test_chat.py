import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import chat


class BuildMessages(unittest.TestCase):
    def test_user_only(self):
        self.assertEqual(chat.build_messages("hi"), [{"role": "user", "content": "hi"}])

    def test_with_system(self):
        msgs = chat.build_messages("hi", system="be brief")
        self.assertEqual(msgs, [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hi"},
        ])


if __name__ == "__main__":
    unittest.main()
