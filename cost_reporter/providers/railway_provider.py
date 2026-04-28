from __future__ import annotations

import logging
from datetime import date
from typing import Any

from cost_reporter.providers.base import CostProvider, CostResult

logger = logging.getLogger(__name__)

RAILWAY_API_URL = "https://backboard.railway.com/graphql/v2"


class RailwayProvider(CostProvider):
    name = "railway"

    def __init__(
        self,
        api_token: str | None,
        team_id: str | None,
        project_id: str | None,
        workspace_id: str | None,
    ) -> None:
        self.api_token = api_token
        self.team_id = team_id
        self.project_id = project_id
        self.workspace_id = workspace_id

    async def get_daily_cost(self, start_date: date, end_date: date) -> CostResult:
        if not self.api_token:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="skipped",
                details=["RAILWAY_API_TOKEN is not set"],
            )

        if not self.workspace_id:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="skipped",
                details=["RAILWAY_WORKSPACE_ID is not set"],
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

        query = """
        query GetRailwayUsage($workspaceId: String!) {
          usage(
            workspaceId: $workspaceId
            measurements: [
              CPU_USAGE
              MEMORY_USAGE_GB
              NETWORK_RX_GB
              NETWORK_TX_GB
              DISK_USAGE_GB
              EPHEMERAL_DISK_USAGE_GB
              BACKUP_USAGE_GB
            ]
          ) {
            measurement
            value
          }
        }
        """

        variables = {
            "workspaceId": self.workspace_id,
        }

        try:
            payload = await graphql_request(self.api_token, query, variables)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Railway GraphQL request failed: %s", exc.__class__.__name__)
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="error",
                details=[f"Railway API error: {exc.__class__.__name__}"],
            )

        if payload.get("errors"):
            message = payload["errors"][0].get("message", "Unknown Railway GraphQL error")
            logger.warning("Railway GraphQL returned errors")
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="warning",
                details=[f"Railway GraphQL returned errors: {message}"],
                raw={"errors": payload.get("errors")},
            )

        total = _extract_railway_usage_total(payload)
        if total is None:
            logger.warning("Railway usage response did not include parseable values")
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="warning",
                details=["Railway usage values missing or schema changed"],
                raw={"data_keys": list(payload.get("data", {}).keys()) if isinstance(payload.get("data"), dict) else []},
            )

        return CostResult(
            provider=self.name,
            total=total,
            currency="USD",
            status="ok",
            details=[f"workspace_id={self.workspace_id}"],
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
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            response.raise_for_status()
            raise RuntimeError("Railway API returned non-JSON response")

        data = response.json()
        if response.status_code >= 400 and not data.get("errors"):
            raise httpx.HTTPStatusError(
                f"Railway API HTTP error {response.status_code}",
                request=response.request,
                response=response,
            )
        return data


def _extract_railway_usage_total(payload: dict[str, Any]) -> float | None:
    usage_rows = payload.get("data", {}).get("usage", []) if isinstance(payload.get("data"), dict) else []
    if not isinstance(usage_rows, list):
        return None

    total = 0.0
    seen = False
    for row in usage_rows:
        if not isinstance(row, dict):
            continue
        value = row.get("value")
        if isinstance(value, (int, float)):
            total += float(value)
            seen = True
        elif isinstance(value, str):
            try:
                total += float(value)
                seen = True
            except ValueError:
                continue

    return total if seen else None
