import os
import unittest
from unittest.mock import patch

from cost_reporter.config import ReporterConfig


class ReporterConfigTests(unittest.TestCase):
    def test_from_env_parses_breakdown_flag_true(self) -> None:
        with patch.dict(os.environ, {"RAILWAY_COST_BREAKDOWN": "true"}, clear=True):
            cfg = ReporterConfig.from_env()
        self.assertTrue(cfg.railway_cost_breakdown)

    def test_from_env_parses_breakdown_flag_false_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = ReporterConfig.from_env()
        self.assertFalse(cfg.railway_cost_breakdown)


if __name__ == "__main__":
    unittest.main()
