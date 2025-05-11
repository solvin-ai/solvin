# Dockerfile for repos_service
FROM python:3.12.7-slim

WORKDIR /app

COPY ../requirements.txt /app/requirements.txt

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8002

CMD ["uvicorn", "repos_service:app", "--host", "0.0.0.0", "--port", "8002"]
