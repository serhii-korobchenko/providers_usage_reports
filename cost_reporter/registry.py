from __future__ import annotations

from cost_reporter.config import ReporterConfig
from cost_reporter.providers.base import CostProvider
from cost_reporter.providers.elevenlabs_provider import ElevenLabsProvider
from cost_reporter.providers.google_cloud_provider import GoogleCloudProvider
from cost_reporter.providers.openai_provider import OpenAIProvider
from cost_reporter.providers.railway_provider import RailwayProvider


def build_providers(config: ReporterConfig) -> list[CostProvider]:
    providers: list[CostProvider] = []

    for name in config.cost_providers:
        if name == "openai":
            providers.append(OpenAIProvider(config.openai_admin_key, config.openai_cost_group_by))
        elif name == "railway":
            providers.append(
                RailwayProvider(
                    config.railway_api_token,
                    config.railway_team_id,
                    config.railway_project_id,
                    config.railway_workspace_id,
                    config.railway_cost_breakdown,
                )
            )
        elif name == "elevenlabs":
            providers.append(ElevenLabsProvider(config.elevenlabs_api_key))
        elif name == "google_cloud":
            providers.append(
                GoogleCloudProvider(
                    billing_project_id=config.gcp_billing_project_id,
                    billing_table=config.gcp_billing_table,
                    credentials_json=config.gcp_credentials_json,
                    credentials_json_b64=config.gcp_credentials_json_b64,
                    credentials_path=config.gcp_credentials_path,
                )
            )

    return providers
