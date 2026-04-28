from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, datetime, timedelta

from cost_reporter.config import ReporterConfig
from cost_reporter.providers.base import CostResult
from cost_reporter.registry import build_providers
from cost_reporter.telegram import format_report_message, send_telegram_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("cost_reporter")

# Avoid verbose HTTP logs that may include sensitive URLs/tokens.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily cost reporter")
    parser.add_argument(
        "--date",
        default="yesterday",
        help="Report date in YYYY-MM-DD format or 'yesterday'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send Telegram message, print report only",
    )
    return parser.parse_args()


def resolve_target_date(value: str) -> date:
    if value == "yesterday":
        return date.today() - timedelta(days=1)
    return datetime.strptime(value, "%Y-%m-%d").date()


async def run_report(target_date: date, dry_run: bool = False) -> list[CostResult]:
    config = ReporterConfig.from_env()
    providers = build_providers(config)

    if not providers:
        logger.warning("No providers configured in COST_PROVIDERS")
        return []

    next_date = target_date + timedelta(days=1)
    tasks = [provider.get_daily_cost(target_date, next_date) for provider in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    normalized: list[CostResult] = []
    for provider, result in zip(providers, results, strict=False):
        if isinstance(result, Exception):
            logger.error("Provider crashed: %s (%s)", provider.name, result.__class__.__name__)
            normalized.append(
                CostResult(
                    provider=provider.name,
                    total=None,
                    currency="USD",
                    status="error",
                    details=[f"Unhandled provider exception: {result.__class__.__name__}"],
                )
            )
            continue
        normalized.append(result)

    message = format_report_message(target_date, normalized)

    if dry_run:
        logger.info("Dry run enabled, Telegram send skipped")
        print(message)
        return normalized

    if not config.telegram_bot_token or not config.telegram_chat_id:
        logger.warning("Telegram env not configured, skipping send")
        print(message)
        return normalized

    try:
        await send_telegram_message(config.telegram_bot_token, config.telegram_chat_id, message)
        logger.info("Daily cost report sent to Telegram")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send Telegram message: %s", exc.__class__.__name__)
        raise RuntimeError(f"Telegram send failed: {exc.__class__.__name__}") from exc

    return normalized


def main() -> None:
    args = parse_args()
    target_date = resolve_target_date(args.date)
    asyncio.run(run_report(target_date, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
