# Referidos-Bot
[![](https://badgen.net/badge/icon/github?icon=github&label)](https://github.com/dgongut/referidos-bot)
[![](https://badgen.net/badge/icon/docker?icon=docker&label)](https://hub.docker.com/r/dgongut/referidos-bot)
[![Docker Pulls](https://badgen.net/docker/pulls/dgongut/referidos-bot?icon=docker&label=pulls)](https://hub.docker.com/r/dgongut/referidos-bot/)
[![Docker Stars](https://badgen.net/docker/stars/dgongut/referidos-bot?icon=docker&label=stars)](https://hub.docker.com/r/dgongut/referidos-bot/)
[![Docker Image Size](https://badgen.net/docker/size/dgongut/referidos-bot?icon=docker&label=image%20size)](https://hub.docker.com/r/dgongut/referidos-bot/)
![Github stars](https://badgen.net/github/stars/dgongut/referidos-bot?icon=github&label=stars)
![Github forks](https://badgen.net/github/forks/dgongut/referidos-bot?icon=github&label=forks)
![Github last-commit](https://img.shields.io/github/last-commit/dgongut/referidos-bot)
![Github last-commit](https://badgen.net/github/license/dgongut/referidos-bot)

Genera enlaces de Amazon referidos con tu tag, añade imágenes y pon el precio antiguo y el nuevo

¿Lo buscas en [![](https://badgen.net/badge/icon/docker?icon=docker&label)](https://hub.docker.com/r/dgongut/referidos-bot)?

## Configuración en config.py

| CLAVE  | OBLIGATORIO | VALOR |
|:------------- |:---------------:| :-------------|
|TELEGRAM_TOKEN |✅| Token del bot |
|TZ |✅| Timezone (Por ejemplo Europe/Madrid) |
|IP_RANGE |✅| Rango de IPs a detectar. Por ejemplo 192.168.1.1-192.168.1.255 | 
|X_RAPIDAPI_KEY |✅| API Key de Real-Time Amazon Data en rapidapi.com. La cuenta gratuita deja 100 consultas al mes, en caso de que falle, el bot está preparado para ello y sigue funcionando, solo que no generará la imagen y no podrá el precio anterior ni actual. | 
|TELEGRAM_GROUP_NICK |✅| El nick del grupo, por ejemplo si el grupo es @detrasdelmostrador, habría que poner aquí solamente `detrasdelmostrador`|

### Anotaciones
Será necesario mapear un volumen para almacenar lo que el bot escribe en /app/data

### Ejemplo de Docker-Compose para su ejecución normal

```yaml
services:
    referidos-bot:
        environment:
            - REFERIDO=TAGdeREFERIDO # Aquí has de poner el tag de tu referido, por ejemplo: dgongut-21
            - TELEGRAM_TOKEN=your_telegram_token_here # Aquí has de poner el token de tu bot de Telegram
            - TZ=Europe/Madrid
            - X_RAPIDAPI_KEY=your_rapidapi_key_here # Aquí has de poner tu API Key de real-time-amazon-data en rapidapi.com
            - TELEGRAM_GROUP_NICK=your_telegram_group_nick # Aquí has de poner el nick del grupo de Telegram (se verá en el mensaje)
        volumes:
            - ./ddm.jpg:/config/image.jpg # Cambiar la parte izquierda con una imagen del grupo, ha de ser en formato cuadrado, cambiar solamente la parte izquierda, la derecha hay que dejarla como está /config/image.jpg
        image: dgongut/referidos-bot:latest
        container_name: referidos-bot
        restart: always
        tty: true
```
