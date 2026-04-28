from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date

from cost_reporter.providers.base import CostResult

logger = logging.getLogger(__name__)


def format_report_message(target_date: date, results: list[CostResult]) -> str:
    lines = [f"Щоденний звіт витрат за {target_date.isoformat()}", ""]

    totals_by_currency: dict[str, float] = defaultdict(float)
    for result in results:
        icon = {
            "ok": "✅",
            "warning": "⚠️",
            "error": "❌",
            "skipped": "⚠️",
        }[result.status]

        if result.total is not None and result.status in {"ok", "warning"}:
            lines.append(f"{icon} {pretty_provider_name(result.provider)}: {result.total:.4f} {result.currency}")
            totals_by_currency[result.currency] += result.total
            breakdown_text = result.raw.get("breakdown_text") if isinstance(result.raw, dict) else None
            if isinstance(breakdown_text, str) and breakdown_text.strip():
                lines.append("")
                lines.append(breakdown_text)
        else:
            reason = "; ".join(result.details) if result.details else result.status
            lines.append(f"{icon} {pretty_provider_name(result.provider)}: {result.status} / {reason}")

    lines.append("")
    if totals_by_currency:
        if len(totals_by_currency) == 1:
            currency, value = next(iter(totals_by_currency.items()))
            lines.append(f"Разом: {value:.4f} {currency}")
        else:
            lines.append("Разом:")
            for currency, value in sorted(totals_by_currency.items()):
                lines.append(f"- {value:.4f} {currency}")
    else:
        lines.append("Разом: немає доступних даних")

    return "\n".join(lines)


def pretty_provider_name(provider: str) -> str:
    mapping = {
        "openai": "OpenAI",
        "railway": "Railway",
        "google_cloud": "Google Cloud",
        "elevenlabs": "ElevenLabs",
    }
    return mapping.get(provider, provider)


async def send_telegram_message(bot_token: str, chat_id: str, message: str) -> None:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is required to send Telegram messages") from exc

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.error("Telegram API returned error response")
            raise RuntimeError("Telegram API returned non-ok response")
