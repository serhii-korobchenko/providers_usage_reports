from __future__ import annotations

import logging
from datetime import date
from typing import Any


from cost_reporter.providers.base import CostProvider, CostResult

logger = logging.getLogger(__name__)

RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"


class RailwayProvider(CostProvider):
    name = "railway"

    def __init__(self, api_token: str | None, team_id: str | None, project_id: str | None) -> None:
        self.api_token = api_token
        self.team_id = team_id
        self.project_id = project_id

    async def get_daily_cost(self, start_date: date, end_date: date) -> CostResult:
        if not self.api_token:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="skipped",
                details=["RAILWAY_API_TOKEN is not set"],
            )

        try:
            import httpx  # noqa: F401
        except ImportError:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="warning",
                details=["httpx is not installed"],
            )

        # TODO: Confirm and refine this query against the latest Railway GraphQL billing schema.
        query = """
        query DailyUsage($projectId: String, $teamId: String, $startDate: String!, $endDate: String!) {
          me {
            projects {
              edges {
                node {
                  id
                  name
                  usage(startDate: $startDate, endDate: $endDate) {
                    totalCost
                    currency
                  }
                }
              }
            }
          }
        }
        """

        variables = {
            "projectId": self.project_id,
            "teamId": self.team_id,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        }

        try:
            payload = await graphql_request(self.api_token, query, variables)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Railway GraphQL request failed")
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="error",
                details=[f"Railway API error: {exc.__class__.__name__}"],
            )

        if payload.get("errors"):
            message = payload["errors"][0].get("message", "Unknown Railway GraphQL error")
            logger.warning("Railway GraphQL returned errors: %s", message)
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="warning",
                details=[f"Railway GraphQL returned errors: {message}"],
                raw={"errors": payload.get("errors")},
            )

        total, currency = _extract_railway_cost(payload)
        if total is None:
            logger.warning("Railway response did not include parseable billing fields")
            return CostResult(
                provider=self.name,
                total=None,
                currency=currency or "USD",
                status="warning",
                details=["Railway billing fields missing or schema changed"],
                raw={"data_keys": list(payload.get("data", {}).keys()) if isinstance(payload.get("data"), dict) else []},
            )

        return CostResult(
            provider=self.name,
            total=total,
            currency=currency,
            status="ok",
            details=["Calculated from Railway GraphQL usage fields"],
        )


async def graphql_request(api_token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    import httpx

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables}
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(RAILWAY_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def _extract_railway_cost(payload: dict[str, Any]) -> tuple[float | None, str]:
    currency = "USD"
    total = 0.0
    seen = False

    data = payload.get("data", {})
    projects = (
        data.get("me", {})
        .get("projects", {})
        .get("edges", [])
        if isinstance(data, dict)
        else []
    )

    for edge in projects:
        node = edge.get("node", {}) if isinstance(edge, dict) else {}
        usage = node.get("usage", {}) if isinstance(node, dict) else {}
        if not isinstance(usage, dict):
            continue

        value = usage.get("totalCost") or usage.get("cost")
        if isinstance(value, (int, float)):
            total += float(value)
            seen = True

        usage_currency = usage.get("currency")
        if isinstance(usage_currency, str) and usage_currency:
            currency = usage_currency

    return (total if seen else None, currency)
