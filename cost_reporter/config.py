from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(slots=True)
class ReporterConfig:
    cost_providers: list[str]
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    openai_admin_key: str | None
    openai_cost_group_by: list[str]
    railway_api_token: str | None
    railway_team_id: str | None
    railway_project_id: str | None
    railway_workspace_id: str | None
    gcp_credentials_json: str | None
    gcp_credentials_json_b64: str | None
    gcp_credentials_path: str | None
    gcp_billing_project_id: str | None
    gcp_billing_table: str | None

    @classmethod
    def from_env(cls) -> "ReporterConfig":
        providers_raw = os.getenv("COST_PROVIDERS", "openai,railway,google_cloud")
        cost_providers = [item.strip() for item in providers_raw.split(",") if item.strip()]
        group_by_raw = os.getenv("OPENAI_COST_GROUP_BY", "")
        group_by = [item.strip() for item in group_by_raw.split(",") if item.strip()]

        return cls(
            cost_providers=cost_providers,
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            openai_admin_key=os.getenv("OPENAI_ADMIN_KEY") or os.getenv("OPENAI_ORG_API_KEY"),
            openai_cost_group_by=group_by,
            railway_api_token=os.getenv("RAILWAY_API_TOKEN"),
            railway_team_id=os.getenv("RAILWAY_TEAM_ID"),
            railway_project_id=os.getenv("RAILWAY_PROJECT_ID"),
            railway_workspace_id=os.getenv("RAILWAY_WORKSPACE_ID"),
            gcp_credentials_json=os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"),
            gcp_credentials_json_b64=os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON_B64"),
            gcp_credentials_path=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            gcp_billing_project_id=os.getenv("GCP_BILLING_PROJECT_ID"),
            gcp_billing_table=os.getenv("GCP_BILLING_TABLE"),
        )

    def get_gcp_credentials_info(self) -> tuple[dict | None, str | None]:
        if self.gcp_credentials_json:
            try:
                return json.loads(self.gcp_credentials_json), None
            except json.JSONDecodeError:
                return None, "GOOGLE_APPLICATION_CREDENTIALS_JSON is not valid JSON"
        if self.gcp_credentials_json_b64:
            return None, "GOOGLE_APPLICATION_CREDENTIALS_JSON_B64 is configured (decoded in provider)"
        return None, None
