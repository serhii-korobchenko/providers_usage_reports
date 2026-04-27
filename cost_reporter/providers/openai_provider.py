from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from cost_reporter.providers.base import CostProvider, CostResult

logger = logging.getLogger(__name__)


class OpenAIProvider(CostProvider):
    name = "openai"

    def __init__(self, admin_key: str | None, group_by: list[str] | None = None) -> None:
        self.admin_key = admin_key
        self.group_by = group_by or ["project_id", "line_item"]

    async def get_daily_cost(self, start_date: date, end_date: date) -> CostResult:
        if not self.admin_key:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="skipped",
                details=["OPENAI_ADMIN_KEY or OPENAI_ORG_API_KEY is not set"],
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

        start_ts = int(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())

        headers = {
            "Authorization": f"Bearer {self.admin_key}",
            "Content-Type": "application/json",
        }
        params: list[tuple[str, str | int]] = [
            ("start_time", start_ts),
            ("end_time", end_ts),
            ("bucket_width", "1d"),
        ]
        params.extend(("group_by[]", item) for item in self.group_by)

        url = "https://api.openai.com/v1/organization/costs"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url, headers=headers, params=params)
                if response.status_code == 403:
                    logger.warning("OpenAI Costs API returned 403 (permission denied)")
                    return CostResult(
                        provider=self.name,
                        total=None,
                        currency="USD",
                        status="warning",
                        details=["403 Forbidden: check OPENAI_ORG_API_KEY/OPENAI_ADMIN_KEY org permissions"],
                    )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code if exc.response else "unknown"
            logger.warning("OpenAI Costs API HTTP error: %s", code)
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="error",
                details=[f"OpenAI Costs API HTTP error: {code}"],
            )
        except httpx.HTTPError as exc:
            logger.warning("OpenAI Costs API request error: %s", exc.__class__.__name__)
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="error",
                details=[f"OpenAI Costs API request error: {exc.__class__.__name__}"],
            )

        total, currency = _extract_total_from_payload(payload)
        if total is None:
            return CostResult(
                provider=self.name,
                total=None,
                currency=currency or "USD",
                status="warning",
                details=["Could not parse total from OpenAI API response"],
                raw={"keys": list(payload.keys())},
            )

        return CostResult(
            provider=self.name,
            total=total,
            currency=currency,
            status="ok",
            details=[f"group_by={','.join(self.group_by)}", f"start_time={start_ts}", f"end_time={end_ts}"],
        )


def _extract_total_from_payload(payload: dict[str, Any]) -> tuple[float | None, str]:
    currency = "USD"
    seen = False

    data = payload.get("data", [])
    total = 0.0
    if isinstance(data, list):
        for bucket in data:
            bucket_total = _sum_amounts(bucket)
            if bucket_total is not None:
                total += bucket_total
                seen = True
            row_currency = _extract_currency(bucket)
            if row_currency:
                currency = row_currency

    if not seen:
        amount = _sum_amounts(payload)
        if amount is not None:
            total = amount
            seen = True
        payload_currency = _extract_currency(payload)
        if payload_currency:
            currency = payload_currency

    return (total if seen else None, currency)


def _sum_amounts(obj: Any) -> float | None:
    if isinstance(obj, list):
        subtotal = 0.0
        seen = False
        for item in obj:
            item_value = _sum_amounts(item)
            if item_value is not None:
                subtotal += item_value
                seen = True
        return subtotal if seen else None

    if not isinstance(obj, dict):
        return None

    if isinstance(obj.get("amount"), dict) and isinstance(obj["amount"].get("value"), (int, float)):
        return float(obj["amount"]["value"])

    for key in ("cost", "total", "total_cost", "totalCost", "value"):
        value = obj.get(key)
        if isinstance(value, (int, float)):
            return float(value)

    for key in ("results", "result", "line_items", "items", "data"):
        nested = obj.get(key)
        nested_value = _sum_amounts(nested)
        if nested_value is not None:
            return nested_value

    return None


def _extract_currency(obj: Any) -> str | None:
    if isinstance(obj, list):
        for item in obj:
            value = _extract_currency(item)
            if value:
                return value
        return None

    if not isinstance(obj, dict):
        return None
    for key in ("currency", "currency_code"):
        value = obj.get(key)
        if isinstance(value, str) and value:
            return value
    amount = obj.get("amount")
    if isinstance(amount, dict):
        currency = amount.get("currency")
        if isinstance(currency, str):
            return currency

    for key in ("results", "result", "data", "items"):
        nested = obj.get(key)
        value = _extract_currency(nested)
        if value:
            return value

    return None
