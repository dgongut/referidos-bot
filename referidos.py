import logging
import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import List, Optional, Tuple
from urllib.parse import quote, urlparse

import requests
import telebot
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, ReplyParameters

from config import REFERIDO, TELEGRAM_GROUP_NICK, TELEGRAM_TOKEN, X_RAPIDAPI_KEY

VERSION = "1.1.0"

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
log = logging.getLogger("referidos")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === CONSTANTES ===

FUENTE = "/usr/share/fonts/dejavu/DejaVuSans.ttf"
FUENTE_NEGRITA = "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
LOGO = "/config/image.jpg"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
TIMEOUT = 10
CACHE_TTL = 3600  # segundos que se reutilizan los datos de un producto para no gastar consultas de la API
CAPTION_MAX = 1024
TEXTO_MAX = 4096

URL_REGEX = re.compile(r'https?://\S+')
ASIN_REGEX = re.compile(r'/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})(?![A-Z0-9])', re.IGNORECASE)
HOSTS_AMAZON = {"amazon.es", "www.amazon.es", "m.amazon.es"}
HOSTS_CORTOS = {"amzn.to", "amzn.eu", "a.co"}
PUNTUACION_FINAL = '.,;:!?)]}>»"\''
MARKDOWN_V2_ESPECIALES = '\\_*[]()~`>#+-=|{}.!'

# === ENLACES ===

def extraer_urls(texto):
    return [url.rstrip(PUNTUACION_FINAL) for url in URL_REGEX.findall(texto)]

def obtener_host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""

def asin_de_url_amazon(url):
    if obtener_host(url) not in HOSTS_AMAZON:
        return None
    match = ASIN_REGEX.search(urlparse(url).path)
    return match.group(1).upper() if match else None

def expandir_url(url):
    try:
        with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, allow_redirects=True, stream=True) as response:
            return response.url
    except requests.RequestException as e:
        log.warning("Error al expandir %s: %s", url, e)
        return None

def obtener_asin(url):
    host = obtener_host(url)
    if host in HOSTS_AMAZON:
        return asin_de_url_amazon(url)
    if host in HOSTS_CORTOS:
        expandida = expandir_url(url)
        return asin_de_url_amazon(expandida) if expandida else None
    return None

def crear_enlace_referido(asin):
    return f"https://www.amazon.es/dp/{asin}?tag={quote(REFERIDO)}"

# === DATOS DEL PRODUCTO ===

@dataclass
class Producto:
    titulo: str
    imagen_url: Optional[str]
    precio: Optional[str]
    precio_original: Optional[str]
    prime: bool

_cache = {}
_cache_lock = threading.Lock()

def formatear_precio(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    return texto if "€" in texto else f"{texto}€"

def obtener_producto(asin):
    ahora = time.monotonic()
    with _cache_lock:
        entrada = _cache.get(asin)
        if entrada and ahora - entrada[0] < CACHE_TTL:
            return entrada[1]

    try:
        response = requests.get(
            "https://real-time-amazon-data.p.rapidapi.com/product-details",
            headers={
                "x-rapidapi-key": X_RAPIDAPI_KEY,
                "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com",
            },
            params={"asin": asin, "country": "ES"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        cuerpo = response.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("No se pudieron obtener los datos de %s: %s", asin, e)
        return None

    datos = cuerpo.get("data") if isinstance(cuerpo, dict) else None
    if not isinstance(datos, dict) or not (datos.get("product_title") or "").strip():
        log.warning("La API no devolvió datos válidos para %s", asin)
        return None

    precio = formatear_precio(datos.get("product_price"))
    precio_original = formatear_precio(datos.get("product_original_price"))
    producto = Producto(
        titulo=datos["product_title"].strip(),
        imagen_url=datos.get("product_photo") or None,
        precio=precio,
        precio_original=precio_original if precio_original != precio else None,
        prime=bool(datos.get("is_prime")),
    )
    with _cache_lock:
        for clave in [k for k, (t, _) in _cache.items() if ahora - t >= CACHE_TTL]:
            del _cache[clave]
        _cache[asin] = (ahora, producto)
    return producto

# === IMAGEN ===

LIENZO = 1000
COLOR_FONDO = (242, 243, 245)
COLOR_TITULO = (31, 41, 55)
COLOR_PIE = (75, 85, 99)
COLOR_PRECIO = (229, 57, 53)
COLOR_PRECIO_ANTERIOR = (255, 215, 213)
COLOR_DESCUENTO = (255, 179, 0)
COLOR_PRIME = (0, 168, 225)

@lru_cache(maxsize=64)
def cargar_fuente(tamaño, negrita=False):
    try:
        return ImageFont.truetype(FUENTE_NEGRITA if negrita else FUENTE, tamaño)
    except OSError:
        return ImageFont.load_default(tamaño)

def ancho_texto(draw, texto, fuente):
    bbox = draw.textbbox((0, 0), texto, font=fuente)
    return bbox[2] - bbox[0]

def fuente_que_quepa(draw, texto, ancho_max, tamaño_max, tamaño_min=20, negrita=False):
    for tamaño in range(tamaño_max, tamaño_min, -2):
        fuente = cargar_fuente(tamaño, negrita)
        if ancho_texto(draw, texto, fuente) <= ancho_max:
            return fuente
    return cargar_fuente(tamaño_min, negrita)

def repartir_en_lineas(draw, texto, fuente, ancho_max, max_lineas):
    """Reparte el texto en líneas que quepan; devuelve None si no cabe en max_lineas."""
    lineas = []
    for palabra in texto.split():
        if lineas and ancho_texto(draw, f"{lineas[-1]} {palabra}", fuente) <= ancho_max:
            lineas[-1] = f"{lineas[-1]} {palabra}"
        else:
            lineas.append(palabra)
        if len(lineas) > max_lineas:
            return None
    return lineas

def titulo_en_lineas(draw, titulo, ancho_max, max_lineas=2):
    for tamaño in range(46, 35, -2):
        fuente = cargar_fuente(tamaño, negrita=True)
        lineas = repartir_en_lineas(draw, titulo, fuente, ancho_max, max_lineas)
        if lineas:
            return lineas, fuente
    # No cabe ni con la fuente mínima: se corta la última línea con puntos suspensivos.
    lineas = []
    for palabra in titulo.split():
        if lineas and ancho_texto(draw, f"{lineas[-1]} {palabra}…", fuente) <= ancho_max:
            lineas[-1] = f"{lineas[-1]} {palabra}"
        elif len(lineas) < max_lineas:
            lineas.append(palabra)
        else:
            break
    lineas[-1] += "…"
    return lineas, fuente

def precio_a_numero(precio):
    try:
        return float(precio.replace("€", "").replace(".", "").replace(",", ".").strip())
    except (AttributeError, ValueError):
        return None

def porcentaje_descuento(producto):
    actual = precio_a_numero(producto.precio)
    anterior = precio_a_numero(producto.precio_original)
    if not actual or not anterior or actual >= anterior:
        return None
    descuento = round((1 - actual / anterior) * 100)
    return descuento if descuento >= 1 else None

def mascara_redondeada(tamaño, radio, escala=4):
    """Máscara con bordes suavizados (se dibuja a mayor tamaño y se reduce)."""
    grande = Image.new("L", (tamaño[0] * escala, tamaño[1] * escala), 0)
    ImageDraw.Draw(grande).rounded_rectangle((0, 0, grande.width - 1, grande.height - 1), radio * escala, fill=255)
    return grande.resize(tamaño, Image.LANCZOS)

def pegar_caja(fondo, caja, radio, color, sombra=False):
    x0, y0, x1, y1 = caja
    tamaño = (x1 - x0, y1 - y0)
    mascara = mascara_redondeada(tamaño, radio)
    if sombra:
        capa = Image.new("L", fondo.size, 0)
        capa.paste(mascara.point(lambda v: v * 45 // 255), (x0, y0 + 10))
        capa = capa.filter(ImageFilter.GaussianBlur(18))
        fondo.paste((0, 0, 0), (0, 0), capa)
    fondo.paste(color, (x0, y0, x1, y1), mascara)

def pegar_etiqueta(fondo, draw, texto, esquina, color_fondo, color_texto, tamaño=34, alinear_derecha=False):
    fuente = cargar_fuente(tamaño, negrita=True)
    ancho, alto = ancho_texto(draw, texto, fuente) + 44, tamaño + 26
    x0 = esquina[0] - ancho if alinear_derecha else esquina[0]
    pegar_caja(fondo, (x0, esquina[1], x0 + ancho, esquina[1] + alto), alto // 2, color_fondo)
    draw.text((x0 + ancho // 2, esquina[1] + alto // 2), texto, font=fuente, fill=color_texto, anchor="mm")

def cargar_logo(tamaño):
    try:
        logo = Image.open(LOGO).convert("RGBA")
    except OSError:
        return None
    lado = min(logo.size)
    logo = logo.crop(((logo.width - lado) // 2, (logo.height - lado) // 2, (logo.width + lado) // 2, (logo.height + lado) // 2))
    logo = logo.resize((tamaño, tamaño), Image.LANCZOS)
    logo.putalpha(Image.composite(logo.getchannel("A"), Image.new("L", logo.size, 0), mascara_redondeada((tamaño, tamaño), tamaño // 2)))
    return logo

def generar_imagen(producto):
    try:
        response = requests.get(producto.imagen_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGBA")

        margen = 40
        fondo = Image.new("RGB", (LIENZO, LIENZO), COLOR_FONDO)
        draw = ImageDraw.Draw(fondo)

        # Título en negrita, hasta dos líneas.
        lineas, fuente_titulo = titulo_en_lineas(draw, producto.titulo, LIENZO - 2 * margen)
        alto_linea = fuente_titulo.size + 10
        y_titulo = 30 + (2 - len(lineas)) * alto_linea // 2
        for i, linea in enumerate(lineas):
            draw.text((margen, y_titulo + i * alto_linea), linea, font=fuente_titulo, fill=COLOR_TITULO)

        # Tarjeta blanca con sombra y el producto centrado dentro.
        tarjeta = (margen, 150, LIENZO - margen, 850)
        pegar_caja(fondo, tarjeta, 36, (255, 255, 255), sombra=True)
        caja_producto = (tarjeta[0] + 50, tarjeta[1] + 80, tarjeta[2] - 50, tarjeta[3] - 70)
        ancho_caja, alto_caja = caja_producto[2] - caja_producto[0], caja_producto[3] - caja_producto[1]
        escala = min(ancho_caja / img.width, alto_caja / img.height)
        img = img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))), Image.LANCZOS)
        fondo.paste(img, (caja_producto[0] + (ancho_caja - img.width) // 2, caja_producto[1] + (alto_caja - img.height) // 2), img)

        # Insignias de descuento y Prime en las esquinas superiores de la tarjeta.
        descuento = porcentaje_descuento(producto)
        if descuento:
            pegar_etiqueta(fondo, draw, f"-{descuento}%", (tarjeta[0] + 24, tarjeta[1] + 24), COLOR_DESCUENTO, COLOR_TITULO)
        if producto.prime:
            pegar_etiqueta(fondo, draw, "✓ prime", (tarjeta[2] - 24, tarjeta[1] + 24), COLOR_PRIME, (255, 255, 255), alinear_derecha=True)

        # Etiqueta de precio abajo a la derecha, montada sobre el borde de la tarjeta.
        relleno = 30
        fuente_precio = fuente_que_quepa(draw, producto.precio, 400, 84, 48, negrita=True)
        ancho_etiqueta = ancho_texto(draw, producto.precio, fuente_precio)
        alto_etiqueta = fuente_precio.size + 2 * relleno
        fuente_anterior = cargar_fuente(36)
        if producto.precio_original:
            ancho_etiqueta = max(ancho_etiqueta, ancho_texto(draw, producto.precio_original, fuente_anterior))
            alto_etiqueta += 46
        etiqueta = (LIENZO - margen - ancho_etiqueta - 2 * relleno, LIENZO - 30 - alto_etiqueta, LIENZO - margen, LIENZO - 30)
        pegar_caja(fondo, etiqueta, 28, COLOR_PRECIO, sombra=True)
        y = etiqueta[1] + relleno
        if producto.precio_original:
            x_anterior = etiqueta[2] - relleno
            draw.text((x_anterior, y), producto.precio_original, font=fuente_anterior, fill=COLOR_PRECIO_ANTERIOR, anchor="ra")
            bbox = draw.textbbox((x_anterior, y), producto.precio_original, font=fuente_anterior, anchor="ra")
            mitad = (bbox[1] + bbox[3]) // 2
            draw.line((bbox[0] - 4, mitad, bbox[2] + 4, mitad), fill=COLOR_PRECIO_ANTERIOR, width=3)
            y += 46
        draw.text((etiqueta[2] - relleno, y), producto.precio, font=fuente_precio, fill=(255, 255, 255), anchor="ra")

        # Pie: logo redondo del grupo y enlace, en el hueco que deja la etiqueta de precio.
        centro_pie = (tarjeta[3] + LIENZO) // 2
        x_pie = margen
        logo = cargar_logo(80)
        if logo:
            fondo.paste(logo, (margen, centro_pie - 40), logo)
            x_pie += 80 + 16
        pie = f"t.me/{TELEGRAM_GROUP_NICK}"
        fuente_pie = fuente_que_quepa(draw, pie, etiqueta[0] - 24 - x_pie, 34, 18, negrita=True)
        draw.text((x_pie, centro_pie), pie, font=fuente_pie, fill=COLOR_PIE, anchor="lm")

        salida = BytesIO()
        fondo.save(salida, format="JPEG", quality=92)
        return salida.getvalue()
    except Exception as e:
        log.warning("No se pudo generar la imagen de %s: %s", producto.titulo, e)
        return None

# === MENSAJE ===

def escapar(texto):
    return "".join(f"\\{c}" if c in MARKDOWN_V2_ESPECIALES else c for c in texto)

def longitud_telegram(texto):
    return len(texto.encode("utf-16-le")) // 2

def recortar(texto, longitud):
    texto = texto[:longitud]
    while longitud_telegram(texto) > longitud:
        texto = texto[:-1]
    return texto

class Mensaje:
    """Construye un texto MarkdownV2 escapando cada fragmento y llevando la cuenta de su longitud visible."""

    def __init__(self):
        self.markdown = []
        self.visible = []

    def añadir(self, texto, marca="", cita=False):
        markdown = f"{marca}{escapar(texto)}{marca}"
        # Dentro de una cita cada línea tiene que empezar por '>'.
        self.markdown.append(markdown.replace("\n", "\n>") if cita else markdown)
        self.visible.append(texto)

    def marcar(self, markdown):
        """Añade marcas de formato que no se ven (inicio y fin de una cita)."""
        self.markdown.append(markdown)

    def añadir_enlace(self, texto, url):
        url_escapada = url.replace("\\", "\\\\").replace(")", "\\)")
        self.markdown.append(f"[{escapar(texto)}]({url_escapada})")
        self.visible.append(texto)

    def extender(self, otro):
        self.markdown += otro.markdown
        self.visible += otro.visible

    def longitud(self):
        return longitud_telegram("".join(self.visible))

    def texto(self):
        return "".join(self.markdown)

def añadir_autor(mensaje, message):
    chat = message.sender_chat
    usuario = message.from_user
    if chat:
        mensaje.añadir(f"@{chat.username}" if chat.username else (chat.title or "Alguien"))
    elif usuario.username:
        mensaje.añadir(f"@{usuario.username}")
    else:
        mensaje.añadir_enlace(usuario.first_name or "Alguien", f"tg://user?id={usuario.id}")

def segmentos_mensaje_original(texto, urls_sustituidas):
    """Trocea el texto original cambiando solo los enlaces sustituidos por un 'enlace' tachado."""
    segmentos, pos = [], 0
    for match in URL_REGEX.finditer(texto):
        url = match.group().rstrip(PUNTUACION_FINAL)
        if url in urls_sustituidas:
            segmentos.append(("", texto[pos:match.start()]))
            segmentos.append(("~", "enlace"))
            pos = match.start() + len(url)
    segmentos.append(("", texto[pos:]))
    if not "".join(t for marca, t in segmentos if not marca).strip():
        return []
    return [(marca, t) for marca, t in segmentos if t]

def construir_mensaje(message, producto, segmentos_originales, limite):
    mensaje = Mensaje()
    mensaje.añadir("🔥 ")
    mensaje.añadir(producto.titulo if producto else "Nueva oferta en Amazon", "*")
    if producto and producto.precio:
        mensaje.añadir("\n\n💰 ")
        mensaje.añadir(producto.precio, "*")
        if producto.precio_original:
            mensaje.añadir("  ")
            mensaje.añadir(producto.precio_original, "~")
            descuento = porcentaje_descuento(producto)
            if descuento:
                mensaje.añadir(f"  (-{descuento}%)")
    if producto and producto.prime:
        mensaje.añadir("\n✅ Prime")

    mensaje.añadir("\n\n👤 ")
    añadir_autor(mensaje, message)

    pie = Mensaje()
    pie.añadir(f"\n\n📢 @{TELEGRAM_GROUP_NICK}")

    if segmentos_originales:
        # El comentario del usuario va en una cita plegable para que un texto largo no ocupe toda la oferta.
        mensaje.añadir(" comenta:\n")
        mensaje.marcar("**>")
        presupuesto = limite - mensaje.longitud() - pie.longitud()
        for marca, texto in segmentos_originales:
            if presupuesto <= 1:
                break
            if longitud_telegram(texto) > presupuesto:
                texto = recortar(texto, presupuesto - 1) + "…"
            mensaje.añadir(texto, marca, cita=True)
            presupuesto -= longitud_telegram(texto)
        mensaje.marcar("||")
    else:
        mensaje.añadir(" la ha compartido")

    mensaje.extender(pie)
    return mensaje.texto()

# === SUSTITUCIÓN ===

@dataclass
class Oferta:
    enlace: str
    imagen: Optional[bytes]
    texto: str

def preparar_oferta(asin, message, segmentos_originales):
    producto = obtener_producto(asin)
    imagen = generar_imagen(producto) if producto and producto.imagen_url and producto.precio else None
    texto = construir_mensaje(message, producto, segmentos_originales, CAPTION_MAX if imagen else TEXTO_MAX)
    return Oferta(crear_enlace_referido(asin), imagen, texto)

def responder_a(message):
    original = message.reply_to_message
    if not original:
        return None
    # En los temas de un foro, los mensajes que no son respuesta apuntan al mensaje que creó el tema.
    if message.is_topic_message and original.message_id == message.message_thread_id:
        return None
    return ReplyParameters(message_id=original.message_id, allow_sending_without_reply=True)

def enviar_oferta(oferta, message):
    opciones = dict(
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Ver oferta en Amazon", url=oferta.enlace)]]),
        parse_mode="MarkdownV2",
        message_thread_id=message.message_thread_id if message.is_topic_message else None,
        reply_parameters=responder_a(message),
    )
    if oferta.imagen:
        foto = BytesIO(oferta.imagen)
        foto.name = "oferta.jpg"
        return bot.send_photo(message.chat.id, foto, caption=oferta.texto, **opciones)
    return bot.send_message(
        message.chat.id,
        oferta.texto,
        link_preview_options=LinkPreviewOptions(url=oferta.enlace, prefer_large_media=True),
        **opciones,
    )

def buscar_asins(texto):
    """Devuelve los ASIN distintos del texto (en orden) y las URLs que se van a sustituir."""
    asins, urls_sustituidas = {}, set()
    for url in extraer_urls(texto):
        asin = obtener_asin(url)
        if asin:
            asins.setdefault(asin, None)
            urls_sustituidas.add(url)
    return list(asins), urls_sustituidas

@bot.message_handler(func=lambda m: m.chat.type in ("group", "supergroup"))
def sustituir_mensaje(message):
    texto = (message.text or "").strip()
    asins, urls_sustituidas = buscar_asins(texto)
    if not asins:
        return

    segmentos = segmentos_mensaje_original(texto, urls_sustituidas)
    # El texto original solo se incluye en la primera oferta para no repetirlo.
    ofertas = [preparar_oferta(asin, message, segmentos if i == 0 else []) for i, asin in enumerate(asins)]

    # Sustitución todo o nada: si algo falla se retiran las ofertas ya publicadas y el original se queda.
    enviados = []
    try:
        for oferta in ofertas:
            enviados.append(enviar_oferta(oferta, message))
        bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        log.error("No se pudo sustituir el mensaje %s del chat %s: %s", message.message_id, message.chat.id, e)
        for enviado in enviados:
            try:
                bot.delete_message(enviado.chat.id, enviado.message_id)
            except Exception as e_borrado:
                log.error("No se pudo retirar la oferta %s: %s", enviado.message_id, e_borrado)
        return
    log.info("Mensaje %s del chat %s sustituido por %d oferta(s): %s", message.message_id, message.chat.id, len(ofertas), ", ".join(asins))

# === INICIO DEL BOT ===

if __name__ == "__main__":
    log.info("Bot iniciado... %s", VERSION)
    bot.infinity_polling()
