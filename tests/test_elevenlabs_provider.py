import unittest

from cost_reporter.providers.elevenlabs_provider import _parse_usage_response


class ElevenLabsProviderTests(unittest.TestCase):
    def test_parse_usage_response(self) -> None:
        payload = {
            "columns": ["timestamp", "total_usage", "total_minutes", "total_cost", "usage_count", "total_charge_count"],
            "rows": [
                ["2026-04-22T00:00:00Z", 0, 0.0, 0.0, 0, 0.0],
                ["2026-04-23T00:00:00Z", 219, 2.44, 0.079716, 3, 1.595],
            ],
            "column_units": [None, "credits", "min", "usd", None, None],
        }

        total_cost, total_usage, currency = _parse_usage_response(payload)

        self.assertAlmostEqual(total_cost or 0.0, 0.079716)
        self.assertEqual(total_usage, 219.0)
        self.assertEqual(currency, "USD")

    def test_parse_empty_rows_returns_zero_cost_not_warning(self) -> None:
        payload = {
            "columns": ["timestamp", "total_usage", "total_cost"],
            "rows": [],
            "column_units": [None, "credits", "usd"],
        }

        total_cost, total_usage, currency = _parse_usage_response(payload)

        self.assertEqual(total_cost, 0.0)
        self.assertEqual(total_usage, 0.0)
        self.assertEqual(currency, "USD")

    def test_parse_nested_data_payload(self) -> None:
        payload = {
            "data": {
                "columns": ["timestamp", "total_usage", "total_cost"],
                "rows": [["2026-04-23T00:00:00Z", "219", "0.079716"]],
                "column_units": [None, "credits", "usd"],
            }
        }

        total_cost, total_usage, currency = _parse_usage_response(payload)

        self.assertAlmostEqual(total_cost or 0.0, 0.079716)
        self.assertEqual(total_usage, 219.0)
        self.assertEqual(currency, "USD")

    def test_parse_exact_empty_response_shape(self) -> None:
        payload = {
            "columns": ["timestamp", "total_usage", "total_minutes", "total_cost", "usage_count", "total_charge_count"],
            "column_types": ["DateTime", "Int", "Float", "Float", "Int", "Float"],
            "rows": [],
            "column_units": [None, "credits", "min", "usd", None, None],
        }

        total_cost, total_usage, currency = _parse_usage_response(payload)

        self.assertEqual(total_cost, 0.0)
        self.assertEqual(total_usage, 0.0)
        self.assertEqual(currency, "USD")


if __name__ == "__main__":
    unittest.main()
