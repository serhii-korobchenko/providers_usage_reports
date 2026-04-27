from __future__ import annotations

import logging
from datetime import date
from typing import Any


from cost_reporter.providers.base import CostProvider, CostResult

logger = logging.getLogger(__name__)


class OpenAIProvider(CostProvider):
    name = "openai"

    def __init__(self, admin_key: str | None, group_by: list[str] | None = None) -> None:
        self.admin_key = admin_key
        self.group_by = group_by or []

    async def get_daily_cost(self, start_date: date, end_date: date) -> CostResult:
        if not self.admin_key:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="skipped",
                details=["OPENAI_ADMIN_KEY is not set"],
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

        headers = {
            "Authorization": f"Bearer {self.admin_key}",
            "Content-Type": "application/json",
        }
        params: dict[str, Any] = {
            "start_time": start_date.isoformat(),
            "end_time": end_date.isoformat(),
        }
        if self.group_by:
            params["group_by"] = ",".join(self.group_by)

        url = "https://api.openai.com/v1/organization/costs"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.exception("OpenAI Costs API request failed")
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="error",
                details=[f"OpenAI Costs API error: {exc.__class__.__name__}"],
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
            details=[f"group_by={','.join(self.group_by)}" if self.group_by else "group_by=none"],
        )


def _extract_total_from_payload(payload: dict[str, Any]) -> tuple[float | None, str]:
    currency = "USD"
    total = 0.0
    seen = False

    entries = payload.get("data", [])
    if isinstance(entries, list):
        for row in entries:
            amount = _extract_amount(row)
            if amount is not None:
                total += amount
                seen = True
            row_currency = _extract_currency(row)
            if row_currency:
                currency = row_currency

    if not seen:
        amount = _extract_amount(payload)
        if amount is not None:
            total = amount
            seen = True
        payload_currency = _extract_currency(payload)
        if payload_currency:
            currency = payload_currency

    return (total if seen else None, currency)


def _extract_amount(obj: Any) -> float | None:
    if not isinstance(obj, dict):
        return None

    for key in ("amount", "cost", "total", "total_cost", "value"):
        value = obj.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            nested = value.get("value")
            if isinstance(nested, (int, float)):
                return float(nested)

    result = obj.get("result")
    if isinstance(result, dict):
        return _extract_amount(result)

    return None


def _extract_currency(obj: Any) -> str | None:
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
    return None
