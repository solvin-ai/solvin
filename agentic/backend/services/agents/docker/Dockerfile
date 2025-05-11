# Dockerfile for agents_service
FROM python:3.12.7-slim

WORKDIR /app

COPY ../src/requirements.txt /app/
COPY ../src /app

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


EXPOSE 8000

# Use uvicorn as the entrypoint for the FastAPI application
CMD ["uvicorn", "agents_service:app", "--host", "0.0.0.0", "--port", "8000"]
