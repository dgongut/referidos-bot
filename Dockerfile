FROM alpine:3.21.3

ARG VERSION=1.1.0
ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache python3 py3-pip tzdata font-dejavu

WORKDIR /app
RUN wget -q https://github.com/dgongut/referidos-bot/archive/refs/tags/v${VERSION}.tar.gz -O /tmp/src.tar.gz \
    && tar -xf /tmp/src.tar.gz -C /tmp \
    && mv /tmp/referidos-bot-${VERSION}/requirements.txt /tmp/referidos-bot-${VERSION}/config.py /tmp/referidos-bot-${VERSION}/referidos.py /app \
    && rm -rf /tmp/src.tar.gz /tmp/referidos-bot-${VERSION} \
    && PIP_BREAK_SYSTEM_PACKAGES=1 pip3 install --no-cache-dir -r requirements.txt

RUN adduser -D -H bot
USER bot

ENTRYPOINT ["python3", "referidos.py"]
