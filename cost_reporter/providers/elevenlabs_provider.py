from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from cost_reporter.providers.base import CostProvider, CostResult

logger = logging.getLogger(__name__)

ELEVENLABS_USAGE_URL = "https://api.elevenlabs.io/v1/workspace/analytics/query/usage-by-product-over-time"


class ElevenLabsProvider(CostProvider):
    name = "elevenlabs"

    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    async def get_daily_cost(self, start_date: date, end_date: date) -> CostResult:
        if not self.api_key:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="skipped",
                details=["ELEVENLABS_API_KEY is not set"],
            )

        try:
            import httpx
        except ImportError:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="warning",
                details=["httpx is not installed"],
            )

        start_ms = _start_of_day_ms(start_date)
        end_ms = _end_of_day_ms(start_date)
        payload = {
            "start_time": start_ms,
            "end_time": end_ms,
            "interval_seconds": 86400,
        }
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(ELEVENLABS_USAGE_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ElevenLabs usage request failed: %s", exc.__class__.__name__)
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="error",
                details=[f"ElevenLabs API request failed: {exc.__class__.__name__}"],
            )

        total_cost, total_usage, currency = _parse_usage_response(data)
        if total_cost is None:
            return CostResult(
                provider=self.name,
                total=None,
                currency=currency,
                status="warning",
                details=["Could not parse total_cost from ElevenLabs response"],
                raw={"keys": list(data.keys()) if isinstance(data, dict) else []},
            )

        return CostResult(
            provider=self.name,
            total=total_cost,
            currency=currency,
            status="ok",
            details=[f"total_usage={total_usage}"],
        )


def _parse_usage_response(data: dict[str, Any]) -> tuple[float | None, float, str]:
    if not isinstance(data, dict):
        return None, 0.0, "USD"

    columns = data.get("columns", [])
    rows = data.get("rows", [])
    units = data.get("column_units", [])
    if not isinstance(columns, list) or not isinstance(rows, list):
        return None, 0.0, "USD"

    try:
        cost_idx = columns.index("total_cost")
    except ValueError:
        return None, 0.0, "USD"

    usage_idx = columns.index("total_usage") if "total_usage" in columns else None

    currency = "USD"
    if isinstance(units, list) and cost_idx < len(units):
        unit = units[cost_idx]
        if isinstance(unit, str) and unit.strip():
            currency = unit.strip().upper()

    total_cost = 0.0
    total_usage = 0.0
    seen = False

    for row in rows:
        if not isinstance(row, list):
            continue
        if cost_idx >= len(row):
            continue

        try:
            total_cost += float(row[cost_idx])
            seen = True
        except (TypeError, ValueError):
            continue

        if usage_idx is not None and usage_idx < len(row):
            try:
                total_usage += float(row[usage_idx])
            except (TypeError, ValueError):
                pass

    return (total_cost if seen else None, total_usage, currency)


def _start_of_day_ms(day: date) -> int:
    dt = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _end_of_day_ms(day: date) -> int:
    dt = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) - timedelta(milliseconds=1)
    return int(dt.timestamp() * 1000)
