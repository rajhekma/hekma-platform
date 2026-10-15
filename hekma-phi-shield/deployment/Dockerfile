FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] pydantic aiofiles pydantic-settings python-multipart \
    torch transformers tokenizers safetensors numpy faker cryptography openai

COPY api/ api/
COPY models/roberta-pii-synthetic/ models/roberta-pii-synthetic/
COPY data/ data/

ENV PYTHONUNBUFFERED=1
ENV ENVIRONMENT=production

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
