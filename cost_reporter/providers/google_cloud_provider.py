from __future__ import annotations

import json
import logging
from datetime import date

from cost_reporter.providers.base import CostProvider, CostResult

logger = logging.getLogger(__name__)


class GoogleCloudProvider(CostProvider):
    name = "google_cloud"

    def __init__(
        self,
        billing_project_id: str | None,
        billing_table: str | None,
        credentials_json: str | None,
        credentials_path: str | None,
    ) -> None:
        self.billing_project_id = billing_project_id
        self.billing_table = billing_table
        self.credentials_json = credentials_json
        self.credentials_path = credentials_path

    async def get_daily_cost(self, start_date: date, end_date: date) -> CostResult:
        missing = []
        if not self.billing_project_id:
            missing.append("GCP_BILLING_PROJECT_ID")
        if not self.billing_table:
            missing.append("GCP_BILLING_TABLE")
        if not self.credentials_json and not self.credentials_path:
            missing.append("GOOGLE_APPLICATION_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS")

        if missing:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="skipped",
                details=[f"Missing required env: {', '.join(missing)}"],
            )

        try:
            from google.cloud import bigquery
            from google.oauth2 import service_account
        except ImportError:
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="warning",
                details=["google-cloud-bigquery is not installed"],
            )

        try:
            if self.credentials_json:
                info = json.loads(self.credentials_json)
                credentials = service_account.Credentials.from_service_account_info(info)
            else:
                credentials = service_account.Credentials.from_service_account_file(self.credentials_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to initialize GCP credentials")
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="error",
                details=[f"Invalid GCP credentials: {exc.__class__.__name__}"],
            )

        sql = f"""
        SELECT SUM(cost) AS total_cost
        FROM `{self.billing_table}`
        WHERE DATE(usage_start_time) = @target_date
        """

        try:
            client = bigquery.Client(project=self.billing_project_id, credentials=credentials)
            config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("target_date", "DATE", start_date.isoformat())
                ]
            )
            query_job = client.query(sql, job_config=config)
            rows = list(query_job.result())
            total = float(rows[0].total_cost or 0.0) if rows else 0.0
        except Exception as exc:  # noqa: BLE001
            logger.exception("BigQuery billing query failed")
            return CostResult(
                provider=self.name,
                total=None,
                currency="USD",
                status="error",
                details=[f"BigQuery query failed: {exc.__class__.__name__}"],
            )

        return CostResult(
            provider=self.name,
            total=total,
            currency="USD",
            status="ok",
            details=[f"Query window: {start_date.isoformat()}"],
        )
