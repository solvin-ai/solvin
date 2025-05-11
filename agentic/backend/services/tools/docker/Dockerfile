# Dockerfile for tools_service
FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
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
        python3-pip \
        sudo \
        tree \
        unzip \
        vim \
        wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages fastapi uvicorn
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY .. /app
COPY ../requirements.txt /app/requirements.txt

WORKDIR /app
VOLUME /app

EXPOSE 8001

CMD ["uvicorn", "tools_service:app", "--host", "0.0.0.0", "--port", "8001"]
