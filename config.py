import os
import sys

# DOCKER ENVIRONMENT VARIABLES
def _obligatoria(nombre):
    valor = (os.environ.get(nombre) or "").strip()
    if not valor:
        sys.exit(f"Falta la variable de entorno obligatoria {nombre}")
    return valor

TELEGRAM_TOKEN = _obligatoria("TELEGRAM_TOKEN")
REFERIDO = _obligatoria("REFERIDO")
X_RAPIDAPI_KEY = _obligatoria("X_RAPIDAPI_KEY")
TELEGRAM_GROUP_NICK = _obligatoria("TELEGRAM_GROUP_NICK").lstrip("@")
