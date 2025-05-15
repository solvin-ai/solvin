# docker/Dockerfile

FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends wget curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/repos/src/requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY services/repos/src/ ./
COPY services/agents/src/shared/ ./shared/

EXPOSE 8002

CMD ["uvicorn", "service_repos:app", \
     "--host", "0.0.0.0", \
     "--port", "8002"]
