# Dockerfile for configs_service
FROM python:3.12.7-slim

WORKDIR /app

COPY ../src/modules /app
COPY ../src/configs_service.py .config.yml requirements.txt /app

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

EXPOSE 8010

CMD ["uvicorn", "configs_service:app", "--host", "0.0.0.0", "--port", "8010"]
