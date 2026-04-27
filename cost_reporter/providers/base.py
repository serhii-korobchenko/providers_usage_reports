from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal


Status = Literal["ok", "warning", "error", "skipped"]


@dataclass(slots=True)
class CostResult:
    provider: str
    total: float | None
    currency: str = "USD"
    status: Status = "ok"
    details: list[str] = field(default_factory=list)
    raw: dict[str, Any] | None = None


class CostProvider:
    name: str = "base"

    async def get_daily_cost(self, start_date: date, end_date: date) -> CostResult:
        raise NotImplementedError
