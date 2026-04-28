from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
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

        total, currency, non_empty_buckets = _extract_total_from_payload(payload)
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
            details=[
                f"group_by={','.join(self.group_by)}",
                f"start_time={start_ts}",
                f"end_time={end_ts}",
                f"non_empty_buckets={non_empty_buckets}",
            ],
        )


def _extract_total_from_payload(payload: dict[str, Any]) -> tuple[float | None, str, int]:
    """Parse OpenAI costs page/bucket schema.

    Expected shape:
      {"data": [{"object": "bucket", "results": [{"amount": {"value": "...", "currency": "usd"}}]}]}
    """
    data = payload.get("data")
    if not isinstance(data, list):
        return None, "USD", 0

    total = Decimal("0")
    currency = "USD"
    seen_any_amount = False
    non_empty_buckets = 0

    for bucket in data:
        if not isinstance(bucket, dict):
            continue
        results = bucket.get("results", [])
        if not isinstance(results, list) or not results:
            continue

        bucket_had_amount = False
        for result in results:
            if not isinstance(result, dict):
                continue
            amount = result.get("amount")
            if not isinstance(amount, dict):
                continue

            value = amount.get("value")
            parsed = _to_decimal(value)
            if parsed is None:
                continue

            total += parsed
            seen_any_amount = True
            bucket_had_amount = True

            result_currency = amount.get("currency")
            if isinstance(result_currency, str) and result_currency:
                currency = result_currency.upper()

        if bucket_had_amount:
            non_empty_buckets += 1

    if not seen_any_amount:
        return 0.0, currency, 0

    return float(total), currency, non_empty_buckets


def _to_decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            return None
    return None
