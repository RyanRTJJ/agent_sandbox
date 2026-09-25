FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 1000 --create-home agent \
 && mkdir /workspace \
 && chown agent:agent /workspace

USER agent
WORKDIR /workspace
ENV HOME=/tmp

CMD ["sleep", "infinity"]