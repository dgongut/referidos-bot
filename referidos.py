import telebot
from telebot.types import InlineKeyboardMarkup
from telebot.types import InlineKeyboardButton
import re
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from config import *
import random

bot = telebot.TeleBot(TELEGRAM_TOKEN)

VERSION = "1.0.1"

# === REGEX ===
amazon_dp_regex = re.compile(
    r'https?://(?:www\.)?amazon\.(?:[a-z\.]{2,6})/(?:.*/)?(?:dp|gp/(?:product|aw/d))/([A-Z0-9]{10})',
    re.IGNORECASE
)
short_amazon_regex = re.compile(r'https?://(?:amzn\.to|amzn\.eu)/\S+')

# === FUNCIONES ===

def expandir_url(url):
    try:
        print(f"Expandiendo URL: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        }
        # Usamos GET para seguir la redirección
        response = requests.get(url, allow_redirects=True, timeout=10, headers=headers)
        final_url = response.url
        print(f"URL expandida a: {final_url}")
        return final_url
    except requests.RequestException as e:
        print(f"Error al expandir URL: {e}")
        return url

def get_asin_from_html(url):
    try:
        print(f"Obteniendo ASIN desde HTML de: {url}")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        # Buscamos el ASIN en el HTML
        match = re.search(r'/dp/([A-Z0-9]{10})', response.url)
        if match:
            asin = match.group(1)
            print(f"ASIN desde HTML: {asin}")
            return asin
        print("No se encontró ASIN en HTML.")
    except Exception as e:
        print(f"Error al obtener ASIN desde HTML: {e}")
    return None

def obtener_asin(url):
    # Aquí validamos los enlaces de amzn.to, amzn.eu y amazon.es
    match = amazon_dp_regex.search(url)
    if match:
        # Extraemos el ASIN que está justo después de /dp/
        asin = match.group(1)
        print(f"ASIN directo encontrado: {asin}")
        return asin
    # Si no es un enlace directo, verificamos si es corto
    elif short_amazon_regex.match(url):
        print(f"Enlace corto detectado: {url}")
        expanded_url = expandir_url(url)  # Expande el enlace
        asin = get_asin_from_html(expanded_url)  # Obtiene el ASIN de la URL expandida
        return asin
    else:
        print(f"Enlace no válido para Amazon: {url}")
        return None

def crear_enlace_referido(asin):
    return f'https://www.amazon.es/dp/{asin}?tag={REFERIDO}'

def procesar_imagen(imagen_url, nombre_producto, texto_abajo, precio, ruta_salida="/tmp/producto_con_texto.jpg"):
    # Función auxiliar para obtener tamaño del texto usando textbbox.
    def get_text_size(draw, text, font):
        bbox = draw.textbbox((0, 0), text, font=font)
        ancho = bbox[2] - bbox[0]
        alto = bbox[3] - bbox[1]
        return ancho, alto

    # Limitar el nombre a las primeras 4 palabras y añadir puntos suspensivos.
    nombre_producto = " ".join(nombre_producto.split()[:4]) + "..."

    # Descargar la imagen.
    response = requests.get(imagen_url)
    if response.status_code != 200:
        print("Error al obtener la imagen")
        return
    img = Image.open(BytesIO(response.content))

    # Redimensionar la imagen para que su ancho o alto no superen 800 píxeles, manteniendo la proporción.
    max_ancho, max_alto = 800, 800
    if img.width > img.height:
        nuevo_ancho = max_ancho
        nuevo_alto = int((max_ancho / img.width) * img.height)
    else:
        nuevo_alto = max_alto
        nuevo_ancho = int((max_alto / img.height) * img.width)
    img_redimensionada = img.resize((nuevo_ancho, nuevo_alto))

    # Crear un fondo blanco de 1000x1000 píxeles y centrar la imagen redimensionada en él.
    fondo = Image.new("RGB", (1000, 1000), (255, 255, 255))
    pos_x = (fondo.width - nuevo_ancho) // 2
    pos_y = (fondo.height - nuevo_alto) // 2
    fondo.paste(img_redimensionada, (pos_x, pos_y))

    # Cargar la fuente Arial (para el nombre) o la fuente por defecto si falla.
    try:
        fuente = ImageFont.truetype("/app/Arial.ttf", 50)
    except IOError:
        fuente = ImageFont.load_default()
    draw = ImageDraw.Draw(fondo)

    # Calcular el tamaño del nombre del producto y centrarlo en la parte superior.
    ancho_nombre, alto_nombre = get_text_size(draw, nombre_producto, fuente)
    pos_nombre = ((fondo.width - ancho_nombre) // 2, 10)
    draw.text(pos_nombre, nombre_producto, font=fuente, fill=(0, 0, 0))

    # Añadir la imagen redimensionada a 100x100 píxeles en la esquina inferior izquierda.
    try:
        img_ddm = Image.open("/config/image.jpg").resize((100, 100))
        pos_ddm = (20, fondo.height - 120)
        fondo.paste(img_ddm, pos_ddm)
    except IOError:
        print("No se pudo cargar la imagen")
        img_ddm = None
        pos_ddm = (20, fondo.height - 120)

    # Preparar y añadir el precio en la esquina inferior derecha con una fuente de tamaño 40.
    try:
        fuente_precio = ajustar_fuente_precio(precio)
    except IOError:
        fuente_precio = ImageFont.load_default()
    ancho_precio, alto_precio = get_text_size(draw, precio, fuente_precio)
    pos_precio = (fondo.width - ancho_precio - 20, fondo.height - alto_precio - 20)
    draw.text(pos_precio, precio, font=fuente_precio, fill=(255, 0, 0))

    # Añadir el texto adicional a la derecha de la imagen, centrándolo verticalmente.
    ancho_texto, alto_texto = get_text_size(draw, texto_abajo, fuente)
    altura_ddm = 100 if img_ddm is None else img_ddm.height
    pos_texto = (pos_ddm[0] + 100 + 10, pos_ddm[1] + (altura_ddm - alto_texto) // 2)
    draw.text(pos_texto, texto_abajo, font=fuente, fill=(0, 0, 0))

    # Guardar la imagen final.
    fondo.save(ruta_salida)
    return ruta_salida

def obtener_detalles_producto(asin, pais='ES'):
    url = "https://real-time-amazon-data.p.rapidapi.com/product-details"
    querystring = {"asin": asin, "country": pais}
    headers = {
        "x-rapidapi-key": X_RAPIDAPI_KEY,
        "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
    }

    response = requests.get(url, headers=headers, params=querystring)

    if response.status_code == 200:
        data = response.json()
        producto = data.get("data", {})
        titulo = producto.get("product_title")
        imagen = producto.get("product_photo")
        precio_actual = agregar_simbolo_euro(producto.get("product_price"))
        precio_original = agregar_simbolo_euro(producto.get("product_original_price"))
        amazon_prime = producto.get("is_prime")
        return titulo, imagen, precio_actual, precio_original, amazon_prime
    else:
        print(f"Error al obtener los detalles del producto: {response.status_code}")
        return None, None

def agregar_simbolo_euro(texto):
    if texto is not None and "€" not in texto:
        return f"{texto}€"
    return texto

def ajustar_fuente_precio(precio):
    # Contar los caracteres del precio
    num_caracteres = len(precio) - 2
    if num_caracteres <= 3:
        tamaño = 100
    elif num_caracteres == 4:
        tamaño = 80
    elif num_caracteres == 5:
        tamaño = 75
    elif num_caracteres == 6:
        tamaño = 65
    elif num_caracteres == 7:
        tamaño = 60
    elif num_caracteres >= 8:
        tamaño = 55

    return ImageFont.truetype("/app/Arial.ttf", tamaño)

def tirar_moneda():
    return random.choice([True, False])
    
def escapar_markdown_v2(texto):
    caracteres_especiales = r'[]()`>#+-=.|{}!¡'
    escapado = ''
    for char in texto:
        if char in caracteres_especiales:
            escapado += f'\\{char}'
        else:
            escapado += char
    return escapado

def limpiar_enlaces_si_hay_mas_texto(texto):
    urls = re.findall(r'https?://[^\s]+', texto)
    mensaje_sin_urls = texto
    for url in urls:
        mensaje_sin_urls = mensaje_sin_urls.replace(url, '')
    
    if mensaje_sin_urls.strip():
        mensaje_limpio = texto
        for i, url in enumerate(urls):
            mensaje_limpio = mensaje_limpio.replace(url, f"~enlace~")
        return mensaje_limpio
    else:
        return None

# === MANEJADOR ===

@bot.message_handler(func=lambda m: m.chat.type in ['supergroup', 'group'])
def manejar_mensajes(message):
    texto = message.text or ""
    urls_encontradas = re.findall(r'https?://[^\s]+', texto)
    enlaces_amazon = []

    for url in urls_encontradas:
        if any(d in url for d in ['amazon.es', 'amzn.to', 'amzn.eu']):
            asin = obtener_asin(url)
            if asin:
                enlace_limpio = crear_enlace_referido(asin)
                enlaces_amazon.append(enlace_limpio)
            else:
                print(f"No se pudo obtener el ASIN de: {url}")

    if enlaces_amazon:
        print(f"Número de enlaces detectados: {len(enlaces_amazon)}")
        for enlace in enlaces_amazon:
            print(f"Obteniendo datos del producto: {enlace}")
            titulo_producto = None
            imagen_url = None
            precio_actual = None
            precio_original = None
            amazon_prime = None
            imagen = None
            titulo_producto, imagen_url, precio_actual, precio_original, amazon_prime = obtener_detalles_producto(obtener_asin(enlace))
            if titulo_producto and imagen_url and precio_actual:
                imagen = procesar_imagen(imagen_url, titulo_producto, f"t.me/{TELEGRAM_GROUP_NICK}", precio_actual, "/tmp/ultimo_producto.jpg")

            keyboard = [[InlineKeyboardButton("⚡ Ir a la oferta ⚡ ", url=enlace)]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if imagen:
                borrar = False
                mensaje_original_limpio = limpiar_enlaces_si_hay_mas_texto(texto)

                respuesta = f"⚡@{message.from_user.username} ha compartido esta oferta❗\n\n ♦️_{titulo_producto}_\n\n*Precio:* "
                if precio_original:
                    respuesta = f"{respuesta}~{precio_original}~ ➡️ "
                respuesta = f"{respuesta}*{precio_actual}*"
                if amazon_prime:
                    respuesta = f"{respuesta}\n\n⭐ Amazon Prime: ✅"
                if mensaje_original_limpio:
                    respuesta = escapar_markdown_v2(f"{respuesta}\n\n♦ @{TELEGRAM_GROUP_NICK}\n\nMensaje original: {mensaje_original_limpio}")
                else:
                    respuesta = escapar_markdown_v2(f"{respuesta}\n\n♦ @{TELEGRAM_GROUP_NICK}")
                print(f"Enviando mensaje: {respuesta}")
                try:
                    if hasattr(message, "is_topic_message") and message.is_topic_message:
                        with open(imagen, 'rb') as foto:
                            bot.send_photo(
                                message.chat.id, 
                                foto, 
                                caption=respuesta, 
                                reply_markup=reply_markup,
                                message_thread_id=message.message_thread_id,
                                parse_mode='MarkdownV2'
                            )
                    else:
                        with open(imagen, 'rb') as foto:
                            bot.send_photo(
                                message.chat.id, 
                                foto, 
                                caption=respuesta, 
                                reply_markup=reply_markup,
                                message_thread_id=message.message_thread_id,
                                parse_mode='MarkdownV2'
                            )
                    print(f"Mensaje con foto enviado: {enlace}")
                    borrar = True
                except Exception as e:
                    print(f"Error al enviar mensaje de oferta: {e}")
            else:
                respuesta = escapar_markdown_v2(f"⚡@{message.from_user.username} ha compartido esta oferta❗\n\n♦ @{TELEGRAM_GROUP_NICK}")
                print(f"Enviando mensaje: {respuesta}")
                try:
                    if hasattr(message, "is_topic_message") and message.is_topic_message:
                        bot.send_message(
                            message.chat.id,
                            f"[ ]({enlace}){respuesta}",
                            reply_markup=reply_markup,
                            message_thread_id=message.message_thread_id,
                            parse_mode='MarkdownV2'
                        )
                    else:
                        bot.send_message(
                            message.chat.id,
                            f"[ ]({enlace}){respuesta}",
                            reply_markup=reply_markup,
                            parse_mode='MarkdownV2'
                        )
                    print(f"Mensaje sin foto enviado: {enlace}")
                    borrar = True
                except Exception as e:
                    print(f"Error al enviar mensaje de oferta: {e}")
            if borrar:
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    print(f"Mensaje original eliminado de @{message.from_user.username}: {texto}")
                except Exception as e:
                    print(f"Error eliminando mensaje: {e}")

# === INICIO DEL BOT ===
print(f"Bot iniciado... {VERSION}")
bot.infinity_polling()