import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from snapcal.preflight import collect


class PreflightTests(unittest.TestCase):
    def test_fixture_requires_exactly_one_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runs").mkdir()
            (root / "runs" / "fixture-demo.json").write_text(
                json.dumps({"step": 1, "irreversible": True}) + "\n"
            )
            cfg = SimpleNamespace(
                has_api_key=True, has_holo_cli=True, data_dir=root / "state"
            )
            checks = {name: ok for name, ok, _ in collect(cfg, root)}
            self.assertTrue(checks["Pause-gate fixture"])


if __name__ == "__main__":
    unittest.main()
