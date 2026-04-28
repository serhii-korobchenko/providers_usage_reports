from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

RAILWAY_GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"

MEASUREMENT_CONFIG: dict[str, dict[str, str]] = {
    "CPU_USAGE": {"unit": "usage", "price_env": "RAILWAY_PRICE_CPU_USAGE", "display": "CPU"},
    "MEMORY_USAGE_GB": {
        "unit": "GB",
        "price_env": "RAILWAY_PRICE_MEMORY_USAGE_GB",
        "display": "Memory",
    },
    "NETWORK_RX_GB": {
        "unit": "GB",
        "price_env": "RAILWAY_PRICE_NETWORK_RX_GB",
        "display": "Network RX",
    },
    "NETWORK_TX_GB": {
        "unit": "GB",
        "price_env": "RAILWAY_PRICE_NETWORK_TX_GB",
        "display": "Network TX",
    },
    "DISK_USAGE_GB": {
        "unit": "GB",
        "price_env": "RAILWAY_PRICE_DISK_USAGE_GB",
        "display": "Disk",
    },
    "EPHEMERAL_DISK_USAGE_GB": {
        "unit": "GB",
        "price_env": "RAILWAY_PRICE_EPHEMERAL_DISK_USAGE_GB",
        "display": "Ephemeral Disk",
    },
    "BACKUP_USAGE_GB": {
        "unit": "GB",
        "price_env": "RAILWAY_PRICE_BACKUP_USAGE_GB",
        "display": "Backups",
    },
}


def get_railway_daily_cost_report(target_date: date | None = None) -> dict[str, Any]:
    day = target_date or (date.today() - timedelta(days=1))
    return _build_report_for_date(day)


def _build_report_for_date(target_date: date) -> dict[str, Any]:
    token = os.getenv("RAILWAY_API_TOKEN")
    workspace_id = os.getenv("RAILWAY_WORKSPACE_ID")

    if not token:
        return _error_report(target_date, "RAILWAY_API_TOKEN is not set")
    if not workspace_id:
        return _error_report(target_date, "RAILWAY_WORKSPACE_ID is not set")

    start_date = target_date.isoformat()
    end_date = (target_date + timedelta(days=1)).isoformat()

    query = """
    query UsageByWorkspace($workspaceId: String!, $startDate: DateTime!, $endDate: DateTime!, $measurements: [MetricMeasurement!]!) {
      workspace(id: $workspaceId) {
        usage(startDate: $startDate, endDate: $endDate, measurements: $measurements) {
          measurements {
            measurement
            value
          }
        }
      }
    }
    """

    variables = {
        "workspaceId": workspace_id,
        "startDate": start_date,
        "endDate": end_date,
        "measurements": list(MEASUREMENT_CONFIG.keys()),
    }

    try:
        payload = graphql_request(query, variables, token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Railway usage query failed: %s", exc.__class__.__name__)
        return _error_report(target_date, f"Railway API request failed: {exc.__class__.__name__}")

    errors = payload.get("errors") if isinstance(payload, dict) else None
    if errors:
        logger.warning("Railway GraphQL returned errors")
        return _error_report(target_date, "Railway GraphQL returned errors", raw={"errors": errors})

    usage_map = _extract_usage_map(payload)
    if usage_map is None:
        logger.warning("Could not parse Railway usage measurements from response")
        return _error_report(target_date, "Could not parse Railway usage measurements", raw={"keys": list(payload.keys()) if isinstance(payload, dict) else []})

    items: dict[str, dict[str, float | str]] = {}
    warnings: list[str] = []
    total_cost = 0.0

    for measurement, cfg in MEASUREMENT_CONFIG.items():
        usage = float(usage_map.get(measurement, 0.0))
        if measurement not in usage_map:
            warnings.append(f"measurement {measurement} missing in Railway response")

        price = _get_price(cfg["price_env"], warnings)
        cost = usage * price
        total_cost += cost

        items[measurement] = {
            "usage": usage,
            "unit": cfg["unit"],
            "price": price,
            "cost": cost,
        }

    report = {
        "date": target_date.isoformat(),
        "currency": "USD",
        "total_cost": total_cost,
        "items": items,
        "warnings": warnings,
    }
    report["text"] = format_railway_daily_cost_report(report)
    return report


def format_railway_daily_cost_report(report: dict[str, Any]) -> str:
    dt = report.get("date", "unknown-date")
    items = report.get("items", {})

    def cost(measurement: str) -> float:
        return float(items.get(measurement, {}).get("cost", 0.0))

    def usage(measurement: str) -> float:
        return float(items.get(measurement, {}).get("usage", 0.0))

    lines = [
        f"💰 Railway витрати за {dt}:",
        "",
        f"• Всього за добу: ${float(report.get('total_cost', 0.0)):.2f}",
        "",
        "📊 Розбивка:",
        f"- CPU: ${cost('CPU_USAGE'):.2f}",
        f"- Memory: ${cost('MEMORY_USAGE_GB'):.2f}",
        f"- Network RX: ${cost('NETWORK_RX_GB'):.2f}",
        f"- Network TX: ${cost('NETWORK_TX_GB'):.2f}",
        f"- Disk: ${cost('DISK_USAGE_GB'):.2f}",
        f"- Ephemeral Disk: ${cost('EPHEMERAL_DISK_USAGE_GB'):.2f}",
        f"- Backups: ${cost('BACKUP_USAGE_GB'):.2f}",
        "",
        "📈 Використання ресурсів:",
        f"- CPU: {usage('CPU_USAGE')}",
        f"- Memory: {usage('MEMORY_USAGE_GB')} GB",
        f"- Network RX: {usage('NETWORK_RX_GB')} GB",
        f"- Network TX: {usage('NETWORK_TX_GB')} GB",
        f"- Disk: {usage('DISK_USAGE_GB')} GB",
        f"- Ephemeral Disk: {usage('EPHEMERAL_DISK_USAGE_GB')} GB",
        f"- Backups: {usage('BACKUP_USAGE_GB')} GB",
    ]

    warnings = report.get("warnings", [])
    if warnings:
        lines.extend(["", "⚠️ Попередження:"])
        lines.extend(f"- {w}" for w in warnings)

    return "\n".join(lines)


def graphql_request(query: str, variables: dict[str, Any], api_token: str) -> dict[str, Any]:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required for Railway GraphQL requests") from exc

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {"query": query, "variables": variables}

    with httpx.Client(timeout=30) as client:
        response = client.post(RAILWAY_GRAPHQL_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def _extract_usage_map(payload: dict[str, Any]) -> dict[str, float] | None:
    if not isinstance(payload, dict):
        return None

    measurements = (
        payload.get("data", {})
        .get("workspace", {})
        .get("usage", {})
        .get("measurements", [])
    )
    if not isinstance(measurements, list):
        return None

    usage_map: dict[str, float] = {}
    for item in measurements:
        if not isinstance(item, dict):
            continue
        key = item.get("measurement")
        if not isinstance(key, str):
            continue
        value = item.get("value", 0)
        try:
            usage_map[key] = float(value)
        except (TypeError, ValueError):
            usage_map[key] = 0.0

    return usage_map


def _get_price(env_name: str, warnings: list[str]) -> float:
    raw = os.getenv(env_name)
    if raw in (None, ""):
        warnings.append(f"{env_name} is not set, fallback to 0")
        logger.warning("%s is not set, fallback to 0", env_name)
        return 0.0

    try:
        return float(raw)
    except ValueError:
        warnings.append(f"{env_name} is invalid, fallback to 0")
        logger.warning("%s has invalid value, fallback to 0", env_name)
        return 0.0


def _error_report(target_date: date, message: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    report = {
        "date": target_date.isoformat(),
        "currency": "USD",
        "total_cost": 0.0,
        "items": {
            key: {"usage": 0.0, "unit": cfg["unit"], "price": 0.0, "cost": 0.0}
            for key, cfg in MEASUREMENT_CONFIG.items()
        },
        "warnings": [message],
        "raw": raw or {},
    }
    report["text"] = format_railway_daily_cost_report(report)
    return report
