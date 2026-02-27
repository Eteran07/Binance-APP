import time
import os
import sys
import re
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ================= CONFIGURACIÓN BÁSICA =================
# Pon True cuando lo subas a DigitalOcean. Pon False para probar en tu PC.
MODO_SERVIDOR = False 

TELEGRAM_TOKEN = "8182993320:AAHxJxbhU_jHXcgyWUVsNjOVHnocuh8e0VI"
ID_ADMIN = "1296635329" # Tu ID personal para recibir el QR
GRUPOS_DESTINO = ["-1003515031472", "-1003661835806", "-1003658688165", "-1003662508479"]

# ================= CONFIGURACIÓN TÉCNICA =================
CARPETA_PERFIL = os.path.join(os.getcwd(), "perfil_hibrido_qr")
API_LISTA = "https://c2c.binance.com/bapi/c2c/v2/friendly/c2c/order/match/listUserOrder"
API_CHAT = "https://c2c.binance.com/bapi/c2c/v2/friendly/c2c/chat/getChatMessages"

# Variables Globales de Sesión
SESSION_COOKIES = None
SESSION_CSRF = None
SESSION_HEADERS = None

def enviar_mensaje(texto, chat_id=None):
    destinos = [chat_id] if chat_id else GRUPOS_DESTINO
    for cid in destinos:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                          json={"chat_id": cid, "text": texto, "parse_mode": "HTML"})
        except: pass

def enviar_foto_qr(ruta_imagen):
    """Envía la foto del QR directamente a tu chat privado"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    with open(ruta_imagen, "rb") as img:
        try:
            print("📤 Enviando Captura a Telegram...")
            requests.post(url, data={"chat_id": ID_ADMIN, "caption": "🔑 <b>ACCIÓN REQUERIDA:</b> Escanea el QR si aparece en la imagen."}, files={"photo": img})
        except Exception as e:
            print(f"Error enviando foto: {e}")

def obtener_cookies_con_qr():
    """
    Estrategia Fail-Safe: Toma foto de toda la pantalla pase lo que pase.
    """
    print("🔑 Iniciando Navegador para Login QR...")
    options = Options()
    options.add_argument(f"user-data-dir={CARPETA_PERFIL}")
    
    if MODO_SERVIDOR:
        print("   ⚙️ Modo Servidor (Headless) ACTIVADO")
        options.add_argument("--headless=new") 
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    else:
        print("   ⚙️ Modo PC (Visible) ACTIVADO")
    
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        driver.get("https://accounts.binance.com/es/login")
        time.sleep(5)
        
        # Intentar cerrar cookies si estorban
        try:
            driver.find_element(By.ID, "onetrust-accept-btn-handler").click()
            time.sleep(1)
        except: pass

        # Si estamos en login, intentamos mostrar el QR y TOMAMOS LA FOTO SÍ O SÍ
        if "login" in driver.current_url:
            print("📸 Página de login detectada.")
            
            # Intentar cambiar a pestaña QR (Best Effort)
            try:
                # Busca cualquier cosa que parezca un botón de QR y le da click
                botones_qr = driver.find_elements(By.XPATH, "//*[contains(@class, 'qr') or contains(@data-type, 'qr')]")
                for btn in botones_qr:
                    try: 
                        if btn.is_displayed():
                            btn.click()
                            print("   🖱️ Click intentado en botón QR")
                            time.sleep(2)
                            break
                    except: pass
            except: pass

            # --- MOMENTO CRÍTICO: FOTO DE PANTALLA COMPLETA ---
            # No esperamos a encontrar el elemento. Tomamos la foto de lo que haya.
            archivo_qr = "pantalla_login_full.png"
            driver.save_screenshot(archivo_qr)
            enviar_foto_qr(archivo_qr)
            
            print("⏳ Esperando que escanees el QR (Detectando redirección)...")
            
            # Esperar redirección (2 minutos máx)
            login_exitoso = False
            for i in range(40):
                time.sleep(3)
                # Si la URL cambia y ya no es login, asumimos éxito
                if "login" not in driver.current_url:
                    print("🎉 ¡Redirección detectada!")
                    login_exitoso = True
                    break
                if i % 10 == 0: print(f"   ... esperando ({i*3}s)")
            
            if not login_exitoso:
                print("❌ Tiempo agotado. No se detectó redirección.")
                return None, None

        # Esperar carga final del dashboard
        time.sleep(5)
        print("✅ Sesión activa. Extrayendo cookies...")
        
        # Extraer Cookies
        selenium_cookies = driver.get_cookies()
        cookies_dict = {c['name']: c['value'] for c in selenium_cookies}
        csrf = cookies_dict.get("csrftoken", "")
        
        return cookies_dict, csrf

    except Exception as e:
        print(f"❌ Error Selenium: {e}")
        return None, None
    finally:
        print("🔒 Cerrando navegador...")
        driver.quit()

def actualizar_sesion():
    global SESSION_COOKIES, SESSION_CSRF, SESSION_HEADERS

    cookies, csrf = obtener_cookies_con_qr()

    if cookies:
        SESSION_COOKIES = cookies
        SESSION_CSRF = csrf
        SESSION_HEADERS = {
            "content-type": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "client-type": "web",
            "csrftoken": SESSION_CSRF
        }
        # Verificar si la sesión es válida llamando a la API
        test_ordenes = consultar_api_ordenes()
        if test_ordenes is not None:
            return True
        else:
            print("❌ Sesión obtenida pero inválida. Cookies expiradas.")
            return False
    return False

def consultar_api_ordenes():
    try:
        r = requests.post(API_LISTA, headers=SESSION_HEADERS, cookies=SESSION_COOKIES, json={
            "page": 1, "rows": 10, "tradeType": "SELL", "orderStatus": "PROCESS" 
        }, timeout=10)
        
        data = r.json()
        # Si success es False o code no es 000000, la cookie murió
        if data.get("code") == "000000" and data.get("success") is not False:
            return data.get("data", [])
        return None 
    except: return []

def consultar_api_chat(order_no):
    try:
        r = requests.post(API_CHAT, headers=SESSION_HEADERS, cookies=SESSION_COOKIES, json={
            "orderNumber": order_no, "page": 1, "rows": 20
        }, timeout=10)
        msgs = r.json().get("data", [])
        return " ".join([m.get("content", "") for m in msgs])
    except: return ""

def extraer_info(texto_chat):
    datos = {}
    texto = texto_chat.lower()
    
    if "banesco" in texto: datos["banco"] = "BANESCO"
    elif "mercantil" in texto: datos["banco"] = "MERCANTIL"
    elif "pago movil" in texto: datos["banco"] = "PAGO MOVIL"
    elif "venezuela" in texto: datos["banco"] = "VENEZUELA"
    
    match_ced = re.search(r'[vejpgVEJPG]?[- ]?\d{6,9}', texto_chat)
    if match_ced:
        raw = match_ced.group(0).upper().replace(" ", "").replace("-", "")
        pref = raw[0] if raw[0] in "VEJPG" else "V"
        datos["cedula"] = f"{pref}-{raw[1:] if raw[0] in 'VEJPG' else raw}"
        
    match_tel = re.search(r'(0414|0424|0412|0416|0426)\d{7}', texto)
    if match_tel: datos["telefono"] = match_tel.group(0)
    
    match_cta = re.search(r'\d{20}', texto)
    if match_cta: datos["cuenta"] = match_cta.group(0)
    
    return datos

def main_loop():
    print("🤖 Iniciando Bot QR Híbrido (Modo Fail-Safe)...")

    login_attempts = 0
    if not actualizar_sesion():
        print("❌ No se pudo iniciar sesión. Revisa la captura enviada.")
        return

    enviar_mensaje("✅ <b>Bot Activado.</b> Monitoreando...", ID_ADMIN)
    procesadas = set()

    while True:
        ordenes = consultar_api_ordenes()

        if ordenes is None:
            login_attempts += 1
            if login_attempts > 3:
                print("❌ Máximo de intentos de login alcanzado. Deteniendo bot.")
                enviar_mensaje("❌ <b>Bot Detenido.</b> Máximo de intentos de login.", ID_ADMIN)
                break
            print("🔄 Sesión caducada. Solicitando QR...")
            if actualizar_sesion():
                enviar_mensaje("✅ <b>Sesión Renovada.</b>", ID_ADMIN)
                login_attempts = 0  # Resetear contador en éxito
                continue
            else:
                print("❌ Fallo en renovación. Reintentando en 1 min...")
                time.sleep(60)
                continue

        for ord in ordenes:
            oid = ord.get("orderNumber")
            monto = ord.get("totalPrice")
            
            if oid and oid not in procesadas:
                print(f"🔎 Analizando: {oid}")
                chat_txt = consultar_api_chat(oid)
                datos = extraer_info(chat_txt)
                
                try: m_fmt = f"{float(monto):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                except: m_fmt = monto

                msg = f"🚨 ORDEN: <code>00{oid}</code>\nMONTO: <code>{m_fmt}</code>\n-------------------------\n"
                
                detalles = []
                if datos.get('banco'): detalles.append(f"• <code>{datos['banco']}</code>")
                if datos.get('cedula'): detalles.append(f"• <code>{datos['cedula']}</code>")
                if datos.get('telefono'): detalles.append(f"• <code>{datos['telefono']}</code>")
                if datos.get('cuenta'): detalles.append(f"• <code>{datos['cuenta']}</code>")
                
                if detalles:
                    msg += "\n".join(detalles)
                    enviar_mensaje(msg)
                    procesadas.add(oid)
                    print("✅ Enviado")
                else:
                    print("⏳ Esperando datos...")
        
        time.sleep(5)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Apagando...")