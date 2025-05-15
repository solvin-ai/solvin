# docker/Dockerfile

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bash-completion \
      build-essential \
      curl \
      dnsutils \
      git \
      htop \
      iproute2 \
      iputils-ping \
      jq \
      less \
      lsof \
      man-db \
      net-tools \
      netcat-openbsd \
      procps \
      python3 \
      python3-pip \
      python3-pytest \
      sudo \
      tree \
      unzip \
      vim \
      wget \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/tools/src/requirements.txt ./

RUN python3 -m pip install --upgrade pip \
 && python3 -m pip install --no-cache-dir semgrep \
 && python3 -m pip install --no-cache-dir -r requirements.txt

COPY services/tools/src/ ./
COPY services/tools/src/shared/ ./shared/

EXPOSE 8001

CMD ["uvicorn", "service_tools", "--host", "0.0.0.0", "--port", "8001"]
