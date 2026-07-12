import os
import unittest
from unittest.mock import patch

from snapcal.voice_approval import _synthesise


class VoiceApprovalTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_gradium_key_blocks_action(self):
        with self.assertRaisesRegex(RuntimeError, "irreversible action blocked"):
            _synthesise("Approve?")
