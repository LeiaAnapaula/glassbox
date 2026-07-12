import unittest
from pathlib import Path

from snapcal.whatsapp import answer_confirms_send, build_task


class WhatsAppResultTests(unittest.TestCase):
    def test_requires_explicit_success(self):
        self.assertFalse(answer_confirms_send("Task finished."))
        self.assertTrue(answer_confirms_send("The image was sent successfully."))

    def test_failure_wins_over_success_wording(self):
        self.assertFalse(answer_confirms_send(
            "I could not find the contact, so the image was not sent successfully."
        ))

    def test_task_quotes_contact_and_path(self):
        task = build_task(Path("/tmp/a screenshot.png"), 'Alex "Work"')
        self.assertIn('Alex \\"Work\\"', task)
        self.assertIn("/tmp/a screenshot.png", task)
        self.assertIn("no caption", task)
        self.assertIn("exact displayed name", task)


if __name__ == "__main__":
    unittest.main()
