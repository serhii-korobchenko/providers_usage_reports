FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Secrets must be injected at runtime via platform env vars / secret manager.
CMD ["python", "-m", "cost_reporter.main", "--date", "yesterday"]
