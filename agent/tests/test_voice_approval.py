import unittest
from unittest.mock import patch

from snapcal.voice_approval import _synthesise


class VoiceApprovalTests(unittest.TestCase):
    @patch("snapcal.voice_approval._gradium_key", return_value="")
    def test_missing_gradium_key_blocks_action(self, _mock_key):
        with self.assertRaisesRegex(RuntimeError, "irreversible action blocked"):
            _synthesise("Approve?")
