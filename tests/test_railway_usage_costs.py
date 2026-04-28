import os
import unittest
from datetime import date
from unittest.mock import patch

from cost_reporter.integrations.railway import usage_costs


class RailwayUsageCostsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = patch.dict(
            os.environ,
            {
                "RAILWAY_API_TOKEN": "token",
                "RAILWAY_WORKSPACE_ID": "ws_123",
                "RAILWAY_PRICE_CPU_USAGE": "2.0",
                "RAILWAY_PRICE_MEMORY_USAGE_GB": "1.5",
                "RAILWAY_PRICE_NETWORK_RX_GB": "1.0",
                "RAILWAY_PRICE_NETWORK_TX_GB": "0.5",
                "RAILWAY_PRICE_DISK_USAGE_GB": "0.1",
                "RAILWAY_PRICE_EPHEMERAL_DISK_USAGE_GB": "0.2",
                "RAILWAY_PRICE_BACKUP_USAGE_GB": "0.3",
            },
            clear=True,
        )
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def test_usage_times_price_calculation(self) -> None:
        payload = {
            "data": {
                "workspace": {
                    "usage": {
                        "measurements": [
                            {"measurement": "CPU_USAGE", "value": 2},
                            {"measurement": "MEMORY_USAGE_GB", "value": 3},
                            {"measurement": "NETWORK_RX_GB", "value": 4},
                            {"measurement": "NETWORK_TX_GB", "value": 5},
                            {"measurement": "DISK_USAGE_GB", "value": 6},
                            {"measurement": "EPHEMERAL_DISK_USAGE_GB", "value": 7},
                            {"measurement": "BACKUP_USAGE_GB", "value": 8},
                        ]
                    }
                }
            }
        }

        with patch.object(usage_costs, "graphql_request", return_value=payload):
            report = usage_costs._build_report_for_date(date(2026, 4, 27))

        self.assertAlmostEqual(report["items"]["CPU_USAGE"]["cost"], 4.0)
        self.assertAlmostEqual(report["items"]["MEMORY_USAGE_GB"]["cost"], 4.5)
        self.assertAlmostEqual(report["total_cost"], 19.4)

    def test_missing_price_defaults_to_zero(self) -> None:
        del os.environ["RAILWAY_PRICE_CPU_USAGE"]

        payload = {
            "data": {
                "workspace": {
                    "usage": {"measurements": [{"measurement": "CPU_USAGE", "value": 10}]}
                }
            }
        }

        with patch.object(usage_costs, "graphql_request", return_value=payload):
            report = usage_costs._build_report_for_date(date(2026, 4, 27))

        self.assertEqual(report["items"]["CPU_USAGE"]["price"], 0.0)
        self.assertEqual(report["items"]["CPU_USAGE"]["cost"], 0.0)
        self.assertTrue(any("RAILWAY_PRICE_CPU_USAGE" in w for w in report["warnings"]))

    def test_formatting_telegram_message(self) -> None:
        report = {
            "date": "2026-04-27",
            "currency": "USD",
            "total_cost": 12.34,
            "items": {
                "CPU_USAGE": {"usage": 1.0, "unit": "usage", "price": 2.0, "cost": 2.0},
                "MEMORY_USAGE_GB": {"usage": 2.0, "unit": "GB", "price": 1.0, "cost": 2.0},
                "NETWORK_RX_GB": {"usage": 3.0, "unit": "GB", "price": 1.0, "cost": 3.0},
                "NETWORK_TX_GB": {"usage": 1.0, "unit": "GB", "price": 1.0, "cost": 1.0},
                "DISK_USAGE_GB": {"usage": 1.0, "unit": "GB", "price": 1.0, "cost": 1.0},
                "EPHEMERAL_DISK_USAGE_GB": {"usage": 1.0, "unit": "GB", "price": 1.0, "cost": 1.0},
                "BACKUP_USAGE_GB": {"usage": 2.34, "unit": "GB", "price": 1.0, "cost": 2.34},
            },
            "warnings": [],
        }

        text = usage_costs.format_railway_daily_cost_report(report)

        self.assertIn("💰 Railway витрати за 2026-04-27", text)
        self.assertIn("• Всього за добу: $12.34", text)
        self.assertIn("- CPU: $2.00", text)
        self.assertIn("- Backups: 2.34 GB", text)

    def test_graphql_errors_handling(self) -> None:
        payload = {"errors": [{"message": "Bad query"}]}

        with patch.object(usage_costs, "graphql_request", return_value=payload):
            report = usage_costs._build_report_for_date(date(2026, 4, 27))

        self.assertEqual(report["total_cost"], 0.0)
        self.assertTrue(any("GraphQL" in w for w in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
