import unittest

from snapcal.trace import _is_calendar_commit


class TraceCommitTests(unittest.TestCase):
    def test_calendar_save_click_is_irreversible(self):
        action = {"type": "click_desktop", "target_text": "Save"}
        self.assertTrue(_is_calendar_commit(action, calendar_run=True))

    def test_non_calendar_save_is_not_marked(self):
        action = {"type": "click_desktop", "target_text": "Save"}
        self.assertFalse(_is_calendar_commit(action, calendar_run=False))

    def test_other_calendar_click_is_not_marked(self):
        action = {"type": "click_desktop", "target_text": "Don't switch"}
        self.assertFalse(_is_calendar_commit(action, calendar_run=True))

    def test_answer_step_is_not_marked(self):
        action = {"type": "answer", "target_text": "Save"}
        self.assertFalse(_is_calendar_commit(action, calendar_run=True))


if __name__ == "__main__":
    unittest.main()
