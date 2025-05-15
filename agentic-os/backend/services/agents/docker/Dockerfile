# docker/Dockerfile

FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends wget curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/agents/src/requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY services/agents/src/ ./
COPY services/agents/src/shared/ ./shared/

EXPOSE 8000

CMD ["uvicorn", "service_agents:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
