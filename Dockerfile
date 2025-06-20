FROM alpine:3.21.3

ARG VERSION=1.0.1

WORKDIR /app
RUN wget https://github.com/dgongut/referidos-bot/archive/refs/tags/v${VERSION}.tar.gz -P /tmp
RUN tar -xf /tmp/v${VERSION}.tar.gz
RUN mv referidos-bot-${VERSION}/Arial.ttf /app
RUN mv referidos-bot-${VERSION}/config.py /app
RUN mv referidos-bot-${VERSION}/referidos.py /app
RUN rm /tmp/v${VERSION}.tar.gz
RUN rm -rf referidos-bot-${VERSION}/
RUN apk add --no-cache python3 py3-pip tzdata
RUN export PIP_BREAK_SYSTEM_PACKAGES=1; pip3 install requests==2.32.3 pyTelegramBotAPI==4.26.0 beautifulsoup4==4.13.3 Pillow==11.1.0

ENTRYPOINT ["python3", "referidos.py"]