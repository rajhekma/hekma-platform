FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY migrations ./migrations

EXPOSE 8011

CMD ["uvicorn", "hekma_scanner.main:app", "--host", "0.0.0.0", "--port", "8011"]
