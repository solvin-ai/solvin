# docker/Dockerfile

FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends wget curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/configs/src/requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY services/configs/src/ ./
COPY services/agents/src/shared/ ./shared/

EXPOSE 8010

CMD ["uvicorn", "service_configs:app", \
     "--host", "0.0.0.0", \
     "--port", "8010"]
