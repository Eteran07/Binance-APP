import customtkinter as ctk
import threading
import time
import requests
from PIL import Image
import os
import sys
import re
import psutil
import socket
import subprocess
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, NoSuchWindowException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ================= CONFIGURACIÓN =================
TELEGRAM_TOKEN = "8182993320:AAHxJxbhU_jHXcgyWUVsNjOVHnocuh8e0VI"
ID_ADMIN = "1296635329" # Tu ID personal para recibir el QR

# ================= CONFIGURACIÓN API =================
MODO_SERVIDOR = False  # True para DigitalOcean, False para PC
API_LISTA = "https://c2c.binance.com/bapi/c2c/v2/friendly/c2c/order/match/listUserOrder"
API_CHAT = "https://c2c.binance.com/bapi/c2c/v2/friendly/c2c/chat/getChatMessages"

# Variables Globales de Sesión API
SESSION_COOKIES = None
SESSION_CSRF = None
SESSION_HEADERS = None

# ================= GESTIÓN DE CARPETAS Y DATOS =================
# 1. Definimos la ruta en APPDATA (C:\Users\TuUsuario\AppData\Roaming\Mis_Datos_BinanceBot)
# Esto es ideal porque es una carpeta oculta del sistema hecha para guardar configuraciones sin pedir permisos de admin.
try:
    DIRECTORIO_DATOS = os.path.join(os.environ['APPDATA'], 'Mis_Datos_BinanceBot')
except:
    # Fallback por si acaso falla (no debería en Windows)
    DIRECTORIO_DATOS = os.path.join(os.environ['USERPROFILE'], 'Mis_Datos_BinanceBot')

# 2. Creamos la carpeta automáticamente si no existe
if not os.path.exists(DIRECTORIO_DATOS):
    try:
        os.makedirs(DIRECTORIO_DATOS)
        print(f"📁 Carpeta de datos creada en: {DIRECTORIO_DATOS}")
    except Exception as e:
        print(f"❌ Error creando carpeta de datos: {e}")
        DIRECTORIO_DATOS = "." # En caso de error extremo, usar carpeta actual

# 3. Definimos las rutas completas de los archivos JSON dentro de esa carpeta
ARCHIVO_GRUPOS = os.path.join(DIRECTORIO_DATOS, "grupos_guardados.json")
ARCHIVO_HISTORIAL = os.path.join(DIRECTORIO_DATOS, "historial_ordenes.json")

# 4. Directorio personalizado para ChromeDriver (dentro de DIRECTORIO_DATOS para evitar permisos)
DIRECTORIO_CHROMEDRIVER = os.path.join(DIRECTORIO_DATOS, "chromedriver")
if not os.path.exists(DIRECTORIO_CHROMEDRIVER):
    try:
        os.makedirs(DIRECTORIO_CHROMEDRIVER)
        print(f"📁 Carpeta ChromeDriver creada en: {DIRECTORIO_CHROMEDRIVER}")
    except Exception as e:
        print(f"❌ Error creando carpeta ChromeDriver: {e}")
        DIRECTORIO_CHROMEDRIVER = DIRECTORIO_DATOS  # Fallback

# TUS GRUPOS INICIALES
GRUPOS_ALERTAS_INICIALES = []

# RUTA Y MEMORIA
CARPETA_PERFIL = os.path.join(os.environ['USERPROFILE'], 'DatosBotBinance_V16_Master')
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT_DEBUG = 9222
URL_ORDENES = "https://c2c-admin.binance.com/es/order/pending"

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

class MonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🦅 Binance P2P V28 - OPTIMIZADO")
        self.geometry("1100x800")

        # --- MODIFICACIÓN: Cargar Icono de forma robusta ---
        try:
            # Usamos resource_path para encontrar el icono dentro del .exe temporal
            icon_path = self.resource_path("BINANCE.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            print(f"Nota: No se pudo cargar el icono de ventana: {e}")
        # ---------------------------------------------------

        # Variables
        self.bot_running = False
        self.is_paused = False
        self.driver = None
        self.modo_automatico = True
        self.pending_queue = []
        self.orders_per_group = 1
        self.last_batch_size = 1  # Para evitar logs repetidos
        self.log_pending = False  # Para debounce del log
        self.last_order_time = 0  # Timestamp de la última orden agregada
        self.buffer_time = 20  # Buffer de tiempo en segundos para acumular órdenes
        # Pausa diferida: si una pausa es solicitada mientras se procesa una orden,
        # la aplicamos solo al finalizar el procesamiento actual.
        self.pause_requested = False
        self.processing_order = False

        # Memoria (Carga lo que ya hiciste para no repetir)
        self.ordenes_procesadas = self.cargar_historial()
        self.datos_pendientes = {}
        self.ultimo_orden_detectada = None
        self.indice_grupo = 0
        self.ultimo_update_id = 0

        # Grupos dinámicos
        self.grupos_alertas = []
        self.group_names = []

        # 1. Intentar cargar del archivo json (PERSISTENCIA)
        self.cargar_grupos_guardados()

        # 2. Si no había archivo, usar los INICIALES (si pusiste alguno arriba)
        if not self.grupos_alertas and GRUPOS_ALERTAS_INICIALES:
             self.grupos_alertas = list(GRUPOS_ALERTAS_INICIALES)
             self.group_names = [f"Grupo {i+1}" for i in range(len(self.grupos_alertas))]

        # Mostrar mensaje de bienvenida con info sobre permisos
        print("🦅 Binance Monitor V28 - Optimizado")
        print("💡 Para evitar errores de permisos, ejecuta como administrador si es necesario.")
        print(f"📁 Directorio de datos: {DIRECTORIO_DATOS}")
        print(f"📁 Directorio ChromeDriver: {DIRECTORIO_CHROMEDRIVER}")
        # --- LAYOUT VISUAL ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. BARRA LATERAL (Con Scroll automático para pantallas pequeñas)
        self.sidebar = ctk.CTkScrollableFrame(self, width=230, corner_radius=0) 
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        # === NUEVO BLOQUE: LOGO BINANCE ===
        try:
            # Buscamos la imagen usando la funcion auxiliar
            ruta_imagen = self.resource_path("BINANCE.jpg")
            
            if os.path.exists(ruta_imagen):
                img_data = Image.open(ruta_imagen)
                # Redimensionamos a 140x140 para que quepa bien
                self.logo_img = ctk.CTkImage(light_image=img_data, dark_image=img_data, size=(140, 140))
                
                self.lbl_logo = ctk.CTkLabel(self.sidebar, image=self.logo_img, text="")
                self.lbl_logo.pack(pady=(30, 10)) # Un poco de margen arriba y abajo
        except Exception as e:
            print(f"No se pudo cargar logo: {e}")
        # ==================================

        ctk.CTkLabel(self.sidebar, text="SISTEMA V28", font=("Arial", 20, "bold")).pack(pady=(0,10))

        ctk.CTkLabel(self.sidebar, text="SISTEMA V28", font=("Arial", 20, "bold")).pack(pady=(30,10))

        # Barra de Carga Detallada
        self.progress = ctk.CTkProgressBar(self.sidebar, width=180)
        self.progress.pack(pady=(0, 5))
        self.progress.set(0)
        self.lbl_progress = ctk.CTkLabel(self.sidebar, text="Sistema Listo.", font=("Arial", 10), text_color="gray")
        self.lbl_progress.pack(pady=(0, 20))

        # Botones
        self.btn_start = ctk.CTkButton(self.sidebar, text="▶ INICIAR SISTEMA", fg_color="#2CC985", font=("Arial", 13, "bold"), command=self.iniciar_secuencia_carga)
        self.btn_start.pack(pady=10, padx=20)

        self.btn_pause = ctk.CTkButton(self.sidebar, text="⏸ PAUSAR", fg_color="#F39C12", state="disabled", command=self.alternar_pausa)
        self.btn_pause.pack(pady=10, padx=20)

        self.switch_modo = ctk.CTkSwitch(self.sidebar, text="AUTO-ENVÍO", command=self.toggle_auto, progress_color="#2CC985")
        self.switch_modo.select()
        self.switch_modo.pack(side="bottom", pady=20)

        # Lote por grupo (slider)
        self.lbl_batch = ctk.CTkLabel(self.sidebar, text="Lote por grupo: 1", font=("Arial", 10))
        self.lbl_batch.pack(pady=(0,5))
        self.sld_batch = ctk.CTkSlider(self.sidebar, from_=1, to=10, number_of_steps=9, command=self.change_batch_size)
        self.sld_batch.set(1)
        self.sld_batch.pack(padx=10, pady=(0,10))

        # ============================================================
        # MODIFICACIÓN 1: Reemplaza desde "Selección de grupos" hasta antes de "self.dist_switch"
        # ============================================================
        
        # Selección de grupos
        self.lbl_groups = ctk.CTkLabel(self.sidebar, text="Seleccionar Grupos:", font=("Arial", 10))
        self.lbl_groups.pack(pady=(10,5))

        # --- CAMBIO CLAVE: Creamos un contenedor Scrollable ---
        self.scroll_groups = ctk.CTkScrollableFrame(self.sidebar, height=200, label_text="Canales", fg_color="transparent") 
        self.scroll_groups.pack(fill="x", padx=10, pady=5)
        # ----------------------------------------------------

        self.group_checks = []
        self.selected_groups = list(range(len(self.grupos_alertas))) 
        self.current_single_group = 0
        
        for i in range(len(self.grupos_alertas)):
            var = ctk.BooleanVar(value=True)
            # AHORA EL PADRE ES self.scroll_groups, NO self.sidebar
            chk = ctk.CTkCheckBox(self.scroll_groups, text=self.group_names[i], variable=var, command=self.update_selected_groups)
            chk.pack(pady=2, anchor="w")
            self.group_checks.append((chk, var))

        # 3. Validar nombres online (después de crear group_checks)
        self.fetch_group_names()

        # ... (código anterior del scroll_groups) ...

        # 1. Interruptor de distribuir (Este ya lo tienes)
        self.dist_switch = ctk.CTkSwitch(self.sidebar, text="Distribuir entre grupos", command=self.toggle_distribute)
        self.dist_switch.select()
        self.dist_switch.pack(pady=(10,5))
        self.distribute = True

        # 2. AGREGA O CORRIGE ESTE BLOQUE (El botón de refrescar)
        # ========================================================
        self.btn_refresh_groups = ctk.CTkButton(self.sidebar, text="🔄 Refrescar Grupos", fg_color="#3498DB", command=self.refresh_group_names)
        self.btn_refresh_groups.pack(pady=(0,10)) 
        # ========================================================

        # 3. La etiqueta de estado (Esta va al final)
        self.status_lbl = ctk.CTkLabel(self.sidebar, text="OFFLINE", text_color="gray", font=("Arial", 14, "bold"))
        self.status_lbl.pack(side="bottom", pady=5)



        # 2. LOGS
        self.center = ctk.CTkFrame(self)
        self.center.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(self.center, text="📟 TERMINAL EN VIVO", font=("Consolas", 14, "bold"), text_color="#3498DB").pack(pady=5)
        self.log_box = ctk.CTkTextbox(self.center, font=("Consolas", 12), fg_color="#1E1E1E", text_color="#00FF00")
        self.log_box.pack(fill="both", expand=True, padx=5, pady=5)

        self.frame_conf = ctk.CTkFrame(self.center, fg_color="#222")
        self.frame_conf.pack(fill="x", padx=5, pady=5)
        self.lbl_alert = ctk.CTkLabel(self.frame_conf, text="--", font=("Arial", 12))
        self.lbl_alert.pack(side="left", padx=10, pady=10)
        self.btn_send = ctk.CTkButton(self.frame_conf, text="ENVIAR", state="disabled", fg_color="orange", command=self.enviar_manual)
        self.btn_send.pack(side="right", padx=10, pady=10)
        

# ================= FUNCION AUXILIAR PARA EXE =================
    def resource_path(self, relative_path):
        """ Obtiene ruta absoluta a recursos, funciona para dev y para PyInstaller """
        try:
            # PyInstaller crea una carpeta temporal en _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def verificar_permisos_chromedriver(self):
        """Verifica permisos de escritura en el directorio de ChromeDriver antes de proceder."""
        try:
            test_file = os.path.join(DIRECTORIO_CHROMEDRIVER, "test_write.tmp")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            return True
        except Exception as e:
            self.log(f"⚠️ Verificación de permisos fallida: {e}")
            return False

    # ================= UTILS =================
    def log(self, txt):
        def _log():
            try:
                h = datetime.now().strftime("%H:%M:%S")
                msg = f"[{h}] {txt}"
                self.log_box.insert("end", msg + "\n")
                self.log_box.see("end")
                print(msg)
            except: pass
        self.after(0, _log)

    def update_load_status(self, text, percent):
        self.lbl_progress.configure(text=text)
        self.progress.set(percent)
        self.update_idletasks()



    # ================= MEMORIA (PERSISTENCIA) =================
    def cargar_historial(self):
        if os.path.exists(ARCHIVO_HISTORIAL):
            try:
                with open(ARCHIVO_HISTORIAL, 'r') as f:
                    return set(json.load(f))
            except: return set()
        return set()

    def guardar_orden(self, oid):
        self.ordenes_procesadas.add(oid)
        try:
            with open(ARCHIVO_HISTORIAL, 'w') as f:
                json.dump(list(self.ordenes_procesadas), f)
        except: pass
        
        # ================= PERSISTENCIA DE GRUPOS (NUEVO) =================
    def cargar_grupos_guardados(self):
        """Lee el archivo JSON y restaura los grupos."""
        if os.path.exists(ARCHIVO_GRUPOS):
            try:
                with open(ARCHIVO_GRUPOS, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # data es una lista de dicts: [{"id": "...", "title": "..."}]
                    for item in data:
                        self.grupos_alertas.append(item["id"])
                        # Si tiene título guardado úsalo, sino pon genérico
                        self.group_names.append(item.get("title", f"Grupo {item['id']}"))
                print(f"✅ Se cargaron {len(self.grupos_alertas)} grupos desde {ARCHIVO_GRUPOS}")
            except Exception as e:
                print(f"⚠️ Error cargando grupos guardados: {e}")

    def guardar_grupos_archivo(self):
        """Guarda la lista actual de grupos en un JSON."""
        data = []
        for i in range(len(self.grupos_alertas)):
            try:
                data.append({
                    "id": self.grupos_alertas[i],
                    "title": self.group_names[i]
                })
            except: pass
        try:
            with open(ARCHIVO_GRUPOS, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print("💾 Configuración de grupos guardada.")
        except Exception as e:
            print(f"❌ Error guardando grupos: {e}")

    # ================= GESTIÓN DE GRUPOS (ACTUALIZADA) =================
    def fetch_group_names(self):
        """Fetch group names from Telegram API and update UI. Borra grupos inaccesibles."""
        try:
            cambios = False
            indices_a_eliminar = []

            for i, group_id in enumerate(self.grupos_alertas):
                try:
                    response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat?chat_id={group_id}")
                    
                    # SI EL GRUPO EXISTE (200 OK)
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("ok"):
                            title = data["result"].get("title", f"Grupo {i+1}")
                            # Solo actualizamos y guardamos si el nombre cambió
                            if self.group_names[i] != title:
                                self.group_names[i] = title
                                cambios = True
                                self.log(f"📋 Grupo actualizado: {title}")
                        else:
                            self.log(f"⚠️ Warning Grupo {i+1}: {data.get('description', 'Unknown')}")
                    
                    # SI EL GRUPO YA NO EXISTE O FUE EXPULSADO (400, 403)
                    elif response.status_code in [400, 403]:
                        err_desc = response.json().get('description', 'Desconocido')
                        self.log(f"❌ Grupo eliminado/inaccesible detectado: {self.group_names[i]} ({err_desc})")
                        indices_a_eliminar.append(i)
                        cambios = True
                    else:
                        self.log(f"❌ HTTP Error {response.status_code} verificando grupo {group_id}")

                except Exception as e:
                    self.log(f"❌ Error de conexión para grupo {i+1}: {e}")
                    continue
            
            # PROCESAR ELIMINACIONES (En reverso para no romper indices)
            if indices_a_eliminar:
                for idx in reversed(indices_a_eliminar):
                    rem_name = self.group_names.pop(idx)
                    self.grupos_alertas.pop(idx)
                    self.log(f"🗑️ Eliminando '{rem_name}' de la lista.")
                    
                    # Si ya existen checkboxes (Runtime), eliminarlos de la UI
                    if self.group_checks and idx < len(self.group_checks):
                        chk, var = self.group_checks.pop(idx)
                        chk.destroy()

            # Guardar cambios si hubo
            if cambios:
                self.guardar_grupos_archivo()
                if self.group_checks:
                    self.update_selected_groups()

            # Update checkboxes with names
            if self.group_checks:
                for i, (chk, var) in enumerate(self.group_checks):
                    try:
                        if i < len(self.group_names):
                            chk.configure(text=self.group_names[i])
                    except: pass

        except Exception as e:
            self.log(f"❌ Error general fetching group names: {e}")
            
# ============================================================
    # MODIFICACIÓN 2: Agrega esta función nueva antes de 'detect_new_groups'
    # ============================================================
    def agregar_checkbox_ui(self, chat_id, title):
        """Esta función se ejecuta en el Hilo Principal para no romper la GUI"""
        # Verificar si ya existe
        if str(chat_id) in self.grupos_alertas:
            return

        self.grupos_alertas.append(str(chat_id))
        self.group_names.append(title)
        
        # --- AGREGAR ESTA LÍNEA AQUÍ ---
        self.guardar_grupos_archivo()
        # -------------------------------

        # Crear Checkbox DENTRO del scroll_groups
        var = ctk.BooleanVar(value=True)
        chk = ctk.CTkCheckBox(self.scroll_groups, text=title, variable=var, command=self.update_selected_groups)
        chk.pack(pady=2, anchor="w")
        self.group_checks.append((chk, var))
        
        # Actualizar selección interna
        self.selected_groups.append(len(self.grupos_alertas) - 1)
        self.log(f"🆕 Nuevo grupo detectado y agregado: {title}")

    def refresh_group_names(self):
        """Refresh group names on demand."""
        self.log("🔄 Refrescando nombres de grupos...")
        self.fetch_group_names()
        # Also check for new groups
        self.detect_new_groups()

    # ============================================================
    # MODIFICACIÓN 3: Reemplaza la función 'detect_new_groups' completa
    # ============================================================
    def detect_new_groups(self):
        """Detect new groups where the bot has been added via getUpdates."""
        try:
            offset = self.ultimo_update_id + 1 if self.ultimo_update_id != 0 else 0
            
            response = requests.get(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 2, "allowed_updates": ["message", "my_chat_member"]}
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    for update in data["result"]:
                        self.ultimo_update_id = update["update_id"]
                        
                        chat_id = None
                        title = None
                        
                        # CASO 1: Mensaje en grupo
                        if "message" in update:
                            chat = update["message"].get("chat", {})
                            if chat.get("type") in ["group", "supergroup"]:
                                chat_id = str(chat.get("id"))
                                title = chat.get("title", f"Grupo {chat_id}")

                        # CASO 2: Bot agregado (evento sistema)
                        elif "my_chat_member" in update:
                            chat = update["my_chat_member"].get("chat", {})
                            status = update["my_chat_member"].get("new_chat_member", {}).get("status")
                            if status in ["member", "administrator"] and chat.get("type") in ["group", "supergroup"]:
                                chat_id = str(chat.get("id"))
                                title = chat.get("title", f"Grupo {chat_id}")

                        if chat_id and chat_id not in self.grupos_alertas:
                            # IMPORTANTE: Usar self.after para llamar a la función UI del paso 2
                            self.after(0, lambda c=chat_id, t=title: self.agregar_checkbox_ui(c, t))
                            
        except Exception as e:
            print(f"Error detectando grupos: {e}")

    # ================= CONTROL =================
    def toggle_auto(self):
        self.modo_automatico = bool(self.switch_modo.get())
        self.btn_send.configure(state="disabled" if self.modo_automatico else "normal")
        self.log(f"⚙️ Modo Auto: {'ON' if self.modo_automatico else 'OFF'}")

    def alternar_pausa(self):
        # Si ya estamos en pausa -> reanudar inmediatamente
        if self.is_paused:
            self.is_paused = False
            # Cancelar solicitud pendiente si existiera
            self.pause_requested = False
            self.btn_pause.configure(text="⏸ PAUSAR", fg_color="#F39C12")
            self.status_lbl.configure(text="ONLINE ✅", text_color="#2CC985")
            self.log("▶ Reanudado.")
        else:
            # Si hay una orden en proceso, solicitamos la pausa y la aplicamos
            # cuando termine el procesamiento actual. No interrumpimos la orden.
            try:
                if getattr(self, 'processing_order', False):
                    self.pause_requested = True
                    try:
                        self.btn_pause.configure(text="⏳ APLICANDO PAUSA", fg_color="#F39C12")
                        self.status_lbl.configure(text="PAUSA SOLICITADA", text_color="orange")
                    except: pass
                    self.log("⏳ Pausa solicitada. Se aplicará al finalizar la orden actual.")
                else:
                    # No hay orden en proceso, aplicar pausa inmediatamente
                    self.is_paused = True
                    self.btn_pause.configure(text="▶ REANUDAR", fg_color="green")
                    self.status_lbl.configure(text="EN PAUSA", text_color="orange")
                    self.log("⏸ Pausado.")
            except:
                # Fallback simple
                self.is_paused = True
                self.log("⏸ Pausado.")

    def apply_pending_pause_if_requested(self):
        """Si el usuario solicitó pausa durante el procesamiento, aplicarla ahora.
        Actualiza UI, navega a la lista de órdenes y deja un log de confirmación.
        """
        try:
            if getattr(self, 'pause_requested', False):
                self.pause_requested = False
                self.is_paused = True
                try:
                    self.btn_pause.configure(text="▶ REANUDAR", fg_color="green")
                    self.status_lbl.configure(text="EN PAUSA", text_color="orange")
                except: pass
                # Navegar a la lista para permitir ajustes (scroll, filtros, etc.)
                try:
                    self.driver.get(URL_ORDENES)
                except: pass
                self.log("✅ Pausa aplicada. Distribución ajustada correctamente.")
        except:
            pass

    def reset_estado_bot(self):
        self.bot_running = False
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.driver = None
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled")
        self.status_lbl.configure(text="CHROME CERRADO ❌", text_color="red")
        self.progress.set(0)
        self.lbl_progress.configure(text="Sistema detenido")
        self.log("⚠️ Chrome cerrado. Reinicia.")

    # ================= CONEXIÓN ESTABLE (SUBPROCESS) =================
    def iniciar_secuencia_carga(self):
        if self.bot_running: return

        # Verificar permisos antes de iniciar
        if not self.verificar_permisos_chromedriver():
            self.log("❌ No hay permisos suficientes para ChromeDriver. Ejecuta como administrador.")
            return

        self.btn_start.configure(state="disabled")
        self.bot_running = True
        self.is_paused = False
        threading.Thread(target=self.proceso_carga_backend).start()

    def proceso_carga_backend(self):
        self.log("🚀 Iniciando Sistema...")
        self.update_load_status("Verificando Chrome...", 0.2)
        
        if not self.is_port_open():
            self.log("⚠️ Abriendo Chrome Maestro...")
            self.lanzar_chrome_subprocess()
            time.sleep(4)
        
        self.update_load_status("Conectando...", 0.6)
        try:
            opts = Options()
            opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORT_DEBUG}")
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
            
            self.update_load_status("Verificando...", 0.8)
            encontrado = False
            try:
                # Intentamos encontrar una pestaña que ya tenga Binance abierto y movernos a ella.
                for h in self.driver.window_handles:
                    try:
                        self.driver.switch_to.window(h)
                        cur = self.driver.current_url or ""
                        if "fiatOrder" in cur or "c2c-admin.binance.com" in cur or "binance" in cur:
                            encontrado = True
                            break
                    except:
                        continue
            except: pass
            
            if not encontrado:
                self.log("⚙️ Abriendo/navegando a Binance en la pestaña activa...")
                try:
                    # Preferimos navegar la pestaña actual a la URL de órdenes
                    self.driver.get(URL_ORDENES)
                    time.sleep(1.5)
                except Exception:
                    try:
                        # Si no es posible, abrimos una nueva pestaña y nos movemos a ella
                        self.driver.execute_script(f"window.open('{URL_ORDENES}', '_blank');")
                        time.sleep(1.5)
                        # Cambiamos al último handle (la nueva pestaña)
                        try:
                            self.driver.switch_to.window(self.driver.window_handles[-1])
                        except: pass
                    except Exception as ex:
                        self.log(f"❌ No se pudo abrir Binance: {ex}")

            self.update_load_status("ONLINE", 1.0)
            self.status_lbl.configure(text="ONLINE ✅", text_color="#2CC985")
            self.btn_pause.configure(state="normal")

            # PRIMERO: Esperar a que el usuario complete el login si está en login
            self.log("⏳ Verificando estado de login...")
            login_completado = False
            intentos_login = 0
            while not login_completado and intentos_login < 60:  # Máximo 5 minutos
                current_url = self.driver.current_url.lower()
                if "login" not in current_url and ("fiatOrder" in current_url or "c2c-admin.binance.com" in current_url or "binance" in current_url):
                    login_completado = True
                    self.log("✅ Login completado, procediendo...")
                else:
                    self.log(f"⏳ Esperando login... ({intentos_login * 5}s)")
                    time.sleep(5)
                    intentos_login += 1

            if login_completado:
                # Marcar órdenes pagadas (a liberar) antes de empezar
                self.marcar_ordenes_pagadas()
                self.log("✅ Órdenes pagadas marcadas como procesadas - solo procesaremos órdenes nuevas")
            else:
                self.log("⚠️ Timeout esperando login, iniciando sin marcar órdenes pagadas")

            self.log("✅ Conectado. Escaneando Órdenes Nuevas...")

            threading.Thread(target=self.bucle_principal, daemon=True).start()
            threading.Thread(target=self.bucle_envio_lotes, daemon=True).start()
            threading.Thread(target=self.bucle_deteccion_grupos, daemon=True).start()

        except Exception as e:
            self.log(f"❌ Error: {e}")
            self.reset_estado_bot()

    def is_port_open(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', PORT_DEBUG)) == 0

    def lanzar_chrome_subprocess(self):
        args = [CHROME_PATH, f"--remote-debugging-port={PORT_DEBUG}", f"--user-data-dir={CARPETA_PERFIL}", "--no-first-run", "--start-maximized"]
        subprocess.Popen(args)

    def click_pago_pendiente(self):
        """Intenta hacer clic en la opción 'procesando' para mostrar órdenes en procesamiento."""
        try:
            # Intentar hacer clic en 'procesando'
            xpaths_procesando = [
                "//*[contains(text(), 'procesando')]",
                "//*[contains(text(), 'Procesando')]",
                "//*[contains(text(), 'Processing')]"
            ]
            for xp in xpaths_procesando:
                try:
                    elems = self.driver.find_elements(By.XPATH, xp)
                    for e in elems:
                        try:
                            if e.is_displayed():
                                e.click()
                                time.sleep(1)
                                return True
                        except:
                            continue
                except:
                    continue
        except:
            pass
        return False

    def click_order_element(self, order_id):
        """Hace clic en el elemento de una orden en la nueva interfaz del admin.
        La nueva interfaz es una SPA donde las órdenes se muestran en una lista
        y al hacer clic se abre un panel lateral sin cambiar la URL.
        """
        try:
            self.log(f"🔍 Buscando elemento de orden: {order_id}")
            
            # Estrategias para encontrar y hacer clic en la orden
            estrategias = [
                # Buscar por ID de orden en el texto
                f"//div[contains(@class, 'order') and contains(@class, 'item') and contains(translate(@*, '0123456789', '##########'), '{order_id[:5]}')]",
                # Buscar cualquier elemento que contenga el ID de orden
                f"//*[contains(text(), '{order_id}')]",
                # Buscar en tablas
                f"//table//tr[contains(., '{order_id}')]",
                # Buscar en filas de la lista
                f"//div[contains(@class, 'row') and contains(., '{order_id}')]",
                # Buscar elementos con data-order
                f"//*[@data-order-id='{order_id}']",
                # Buscar elementos con cualquier atributo que contenga el order_id
                f"//*[contains(@*, '{order_id}')]",
            ]
            
            for estrategia in estrategias:
                try:
                    elementos = self.driver.find_elements(By.XPATH, estrategia)
                    for elem in elementos:
                        try:
                            if elem.is_displayed() and elem.is_enabled():
                                # Scroll hacia el elemento
                                self.driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                                time.sleep(0.5)
                                # Intentar clic normal primero
                                elem.click()
                                self.log(f"✅ Clic en orden {order_id} exitoso")
                                time.sleep(2)  # Esperar a que cargue el panel
                                return True
                        except Exception as e:
                            continue
                except:
                    continue
            
            # Si no se encontró por XPath, intentar buscar por texto del ID en la página
            try:
                # Obtener el código corto de la orden (últimos dígitos)
                short_id = order_id[-6:] if len(order_id) >= 6 else order_id
                
                # Buscar elementos que contengan el ID
                elementos_texto = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{short_id}')]")
                for elem in elementos_texto:
                    try:
                        if elem.is_displayed():
                            self.driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            time.sleep(0.3)
                            elem.click()
                            self.log(f"✅ Clic en orden {order_id} exitoso (por texto)")
                            time.sleep(2)
                            return True
                    except:
                        continue
            except:
                pass
                
            self.log(f"⚠️ No se pudo hacer clic en orden {order_id}")
            return False
            
        except Exception as e:
            self.log(f"❌ Error haciendo clic en orden: {e}")
            return False

    def marcar_ordenes_pagadas(self):
        """Accede a la pestaña 'Pagada' y marca todas las órdenes 'a liberar' como procesadas."""
        try:
            # Verificar si estamos en login, si sí, saltar
            current_url = self.driver.current_url.lower()
            if "login" in current_url:
                self.log("⚠️ Usuario en login, saltando marcado de órdenes pagadas")
                return

            self.log("🔄 Accediendo a pestaña 'Pagada' para marcar órdenes pagadas...")

            # Esperar a que la página esté completamente cargada
            try:
                WebDriverWait(self.driver, 15).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                time.sleep(3)  # Espera adicional para elementos dinámicos
            except:
                self.log("⚠️ Timeout esperando carga de página")

            # Intentar hacer clic en la pestaña 'Pagada'
            xpaths_pagada = [
                "//*[contains(text(), 'Pagada')]",
                "//*[contains(text(), 'Pagadas')]",
                "//*[contains(text(), 'Paid')]"
            ]

            pagada_encontrada = False
            for xp in xpaths_pagada:
                try:
                    elems = self.driver.find_elements(By.XPATH, xp)
                    for e in elems:
                        try:
                            if e.is_displayed() and e.is_enabled():
                                e.click()
                                time.sleep(15)  # Esperar más tiempo que cargue la pestaña
                                pagada_encontrada = True
                                break
                        except:
                            continue
                except:
                    continue
                if pagada_encontrada:
                    break

            if not pagada_encontrada:
                self.log("⚠️ No se pudo acceder a la pestaña 'Pagada'")
                return

            # Extraer IDs de órdenes de la pestaña Pagada
            src = self.driver.page_source
            ids_pagadas = re.findall(r'"orderNumber":"(\d{18,20})"', src)
            if not ids_pagadas:
                ids_pagadas = re.findall(r'orderNo=(\d{18,20})', src)

            # Marcar todas como procesadas
            marcadas = 0
            for oid in ids_pagadas:
                if oid not in self.ordenes_procesadas:
                    self.guardar_orden(str(int(oid)))
                    marcadas += 1

            self.log(f"✅ Marcadas {marcadas} órdenes pagadas como procesadas")

            # Volver a la pestaña principal (Todas)
            try:
                xpaths_todas = [
                    "//*[contains(text(), 'Todas')]",
                    "//*[contains(text(), 'All')]",
                    "//*[contains(text(), 'Todas') or contains(text(), 'All')]"
                ]
                for xp in xpaths_todas:
                    try:
                        elems = self.driver.find_elements(By.XPATH, xp)
                        for e in elems:
                            try:
                                if e.is_displayed():
                                    e.click()
                                    time.sleep(1)
                                    break
                            except:
                                continue
                    except:
                        continue
                    break
            except:
                pass

        except Exception as e:
            self.log(f"❌ Error marcando órdenes pagadas: {e}")



    def change_batch_size(self, v):
        try:
            n = int(float(v))
        except:
            n = 1
        if n < 1: n = 1
        self.orders_per_group = n
        try:
            self.lbl_batch.configure(text=f"Lote por grupo: {n}")
        except: pass
        # Log de distribución actualizada solo si cambió y no hay log pendiente
        if n != self.last_batch_size and not self.log_pending:
            self.log_pending = True
            self.after(500, lambda: self.do_log_batch(n))

    def do_log_batch(self, n):
        self.log(f"📊 Distribución actualizada a {n} orden(es) por grupo.")
        self.last_batch_size = n
        self.log_pending = False



    def update_selected_groups(self):
        if not self.distribute:
            checked = [i for i, (chk, var) in enumerate(self.group_checks) if var.get()]
            if checked:
                self.current_single_group = checked[-1]  # Assume last checked is the one clicked
                for i, (chk, var) in enumerate(self.group_checks):
                    if i != self.current_single_group:
                        var.set(False)
                self.selected_groups = [self.current_single_group]
            else:
                self.current_single_group = 0
                self.group_checks[0][1].set(True)
                self.selected_groups = [0]
        else:
            self.selected_groups = [i for i, (chk, var) in enumerate(self.group_checks) if var.get()]
            if not self.selected_groups:
                self.selected_groups = [0]  # default to first

    def toggle_distribute(self):
        self.distribute = bool(self.dist_switch.get())
        self.log(f"Modo distribución: {'Distribuir entre grupos' if self.distribute else 'Enviar todo a un grupo'}")
        self.update_selected_groups()

    def enviar_a_grupo(self, chat_id, datos, oid):
        # Similar a enviar_round_robin pero fuerza envío a grupo específico
        raw_ced = datos.get('cedula', '')
        ced_clean = raw_ced
        if raw_ced:
            c = re.sub(r'[^0-9VEJGPvejgp]', '', raw_ced).upper()
            if len(c) > 4:
                pref = c[0] if c[0] in 'VEJGP' else 'V'
                nums = c[1:] if c[0] in 'VEJGP' else c
                ced_clean = f"{pref}{nums}"
            else:
                ced_clean = raw_ced

        def formatear(v):
            if not v:
                return "0,00"
            raw = str(v)
            clean = re.sub(r'[^0-9\.,]', '', raw)
            try:
                if ',' in clean and '.' in clean:
                    # Determine which separator is thousands/decimal by position
                    if clean.find(',') < clean.find('.'):
                        # e.g. '9,564.96' -> comma thousands, dot decimal
                        clean = clean.replace(',', '')
                    else:
                        # e.g. '9.564,96' -> dot thousands, comma decimal
                        clean = clean.replace('.', '').replace(',', '.')
                elif ',' in clean:
                    parts = clean.split(',')
                    if len(parts[-1]) == 2:
                        # comma used as decimal
                        clean = clean.replace(',', '.')
                    else:
                        # comma as thousands
                        clean = clean.replace(',', '')
                elif '.' in clean:
                    parts = clean.split('.')
                    if len(parts[-1]) == 2:
                        # dot used as decimal (keep)
                        pass
                    else:
                        # dot as thousands
                        clean = clean.replace('.', '')

                val = float(clean)
                s = "{:,.2f}".format(val)
                # Convert en_US formatting (comma thousands, dot decimal)
                # to Venezuelan: dot thousands, comma decimals
                s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
                return s
            except:
                # Fallback: return cleaned string as-is
                return clean

        monto_final = formatear(datos.get('monto', '0'))

        # Format tasa if available
        tasa_final = ""
        if datos.get('tasa'):
            tasa_final = formatear(datos.get('tasa', '0'))

        # AGREGAMOS LOS DOS CEROS AQUI MANUALMENTE
        msg = f"<b>ORDEN:</b> <code>00{oid}</code>\n"
        msg += f"<b>MONTO:</b> <code>{monto_final}</code>\n"
        if tasa_final:
            msg += f"<b>TASA:</b> <code>{tasa_final}</code>\n"
        msg += "------------------\n"
        if datos.get('banco'): msg += f"🏦 <code>{datos.get('banco')}</code>\n"
        msg += f"🆔 <code>{ced_clean}</code>\n"
        if datos.get('telefono'): msg += f"📱 <code>{datos.get('telefono')}</code>\n"
        if datos.get('cuenta'): msg += f"🔢 <code>{datos.get('cuenta')}</code>\n"
        if datos.get('titular'): msg += f"👤 <code>{datos.get('titular')}</code>"

        grupo = chat_id
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={'chat_id': grupo, 'text': msg, 'parse_mode': 'HTML'})
            # Find group number for log
            try:
                group_num = self.grupos_alertas.index(grupo) + 1
                self.log(f"📤 Enviado al Grupo {group_num} (batch)")
            except:
                self.log("📤 Enviado (batch)")

        except:
            self.log("❌ Error Telegram (batch)")

    def bucle_envio_lotes(self):
        # Ciclo que envía órdenes en lote por grupo en estilo round-robin
        # Envía cuando han pasado 20 segundos sin nuevas órdenes, procesando en orden inverso
        last_log_time = 0
        consecutive_errors = 0

        while True:
            if not self.bot_running:
                time.sleep(1)
                continue
            if not self.modo_automatico:
                time.sleep(1)
                continue

            try:
                current_time = time.time()
                time_since_last_order = current_time - self.last_order_time
                queue_len = len(self.pending_queue)

                # Log de estado del buffer cada 5 segundos si hay órdenes acumuladas
                if queue_len > 0 and current_time - last_log_time > 5:
                    remaining_time = max(0, self.buffer_time - time_since_last_order)
                    self.log(f"⏳ Buffer activo: {queue_len} órdenes acumuladas, tiempo restante: {remaining_time:.1f}s")
                    last_log_time = current_time

                # Procesar si han pasado 20 segundos sin nuevas órdenes y hay órdenes en cola
                # O si han pasado más de 5 minutos con órdenes acumuladas (salvaguarda anti-atasco)
                force_send = time_since_last_order >= 300  # 5 minutos
                if queue_len > 0 and (time_since_last_order >= self.buffer_time or force_send):
                    if force_send:
                        self.log(f"🚨 PROCESAMIENTO FORZADO: {queue_len} órdenes acumuladas por más de 5 minutos")
                    else:
                        self.log(f"🚀 Procesando buffer: {queue_len} órdenes en el orden de llegada.")

                    # Usar la cola directamente sin revertir
                    orders_to_send = list(self.pending_queue)
                    self.pending_queue.clear()  # Limpiar la cola original

                    selected_groups_ids = self.selected_groups
                    if not selected_groups_ids:
                        selected_groups_ids = [0]
                    selected_groups = [self.grupos_alertas[i] for i in selected_groups_ids]
                    groups = len(selected_groups)

                    if self.distribute:
                        gi = self.indice_grupo % groups
                        grupo = selected_groups[gi]
                        # send to grupo
                        self.indice_grupo = (self.indice_grupo + 1) % groups
                    else:
                        grupo = selected_groups[0]
                        # send all to grupo

                    # Enviar todas las órdenes en el orden de llegada
                    sent_count = 0
                    for idx, (datos, oid) in enumerate(orders_to_send):
                        try:
                            self.enviar_a_grupo(grupo, datos, oid)
                            self.guardar_orden(oid)
                            sent_count += 1
                            try:
                                group_num = selected_groups_ids[gi] + 1 if self.distribute else self.grupos_alertas.index(grupo) + 1
                                self.log(f"({idx+1}/{queue_len}) Enviado al Grupo {group_num}")
                            except: pass
                        except Exception as e:
                            consecutive_errors += 1
                            self.log(f"❌ Error enviando orden {oid}: {e}")
                            # Reencolar al final para reintentar después
                            try:
                                self.pending_queue.append((datos, oid))
                            except: pass

                    if sent_count > 0:
                        consecutive_errors = 0  # Reset on success
                        self.log(f"✅ Buffer procesado: {sent_count}/{queue_len} órdenes enviadas.")
                    else:
                        self.log(f"❌ No se pudo enviar ninguna orden del buffer ({queue_len} órdenes fallidas)")

                    # Si hay demasiados errores consecutivos, pausar temporalmente
                    if consecutive_errors >= 5:
                        self.log("🚨 Demasiados errores consecutivos, pausando envío por 30 segundos")
                        time.sleep(30)
                        consecutive_errors = 0

                time.sleep(0.5)
            except Exception as e:
                consecutive_errors += 1
                self.log(f"❌ Error en bucle_envio_lotes: {e}")
                if consecutive_errors >= 3:
                    self.log("🚨 Múltiples errores en envío, esperando 10 segundos")
                    time.sleep(10)
                    consecutive_errors = 0
                else:
                    time.sleep(1)

    # ================= BUCLE PRINCIPAL (DETECTA NUEVAS) =================
    def bucle_principal(self):
        last_navigation_check = 0
        stuck_counter = 0

        while self.bot_running:
            if self.is_paused:
                try:
                    self.status_lbl.configure(text="EN PAUSA", text_color="orange")
                except: pass
                time.sleep(1)
                continue

            try:
                current_time = time.time()
                _ = self.driver.window_handles
                url = self.driver.current_url

                # === VERIFICACIÓN ANTI-ATASCO: Forzar retorno a lista cada 60 segundos ===
                if current_time - last_navigation_check > 60:
                    if "orderNo=" in url:
                        self.log("🔄 Verificación anti-atasco: Forzando retorno a lista de órdenes")
                        try:
                            self.driver.get(URL_ORDENES)
                            time.sleep(2)
                            stuck_counter = 0
                        except Exception as e:
                            self.log(f"❌ Error forzando retorno: {e}")
                    last_navigation_check = current_time

                if "login" in url.lower():
                    self.status_lbl.configure(text="LOGIN REQUERIDO", text_color="yellow")
                    time.sleep(2)
                    continue

                # 1. SI ESTAMOS DENTRO DE UNA ORDEN (MANUAL O AUTO)
                if "orderNo=" in url:
                    if self.is_paused:
                        time.sleep(1)
                        continue

                    self.status_lbl.configure(text="ANALIZANDO...", text_color="#3498DB")
                    oid_match = re.search(r'orderNo=(\d+)', url)

                    if oid_match:
                        oid = oid_match.group(1)
                        if oid not in self.ordenes_procesadas:
                            self.log(f"🔎 Analizando ID: {oid}")
                            stuck_counter = 0  # Reset counter on valid processing
                            self.procesar_orden_actual(oid)
                        else:
                            # Orden ya procesada, forzar retorno inmediato
                            self.log(f"⚠️ Orden {oid} ya procesada, retornando a lista")
                            try:
                                self.driver.get(URL_ORDENES)
                            except:
                                pass
                    else:
                        # URL incompleta, esperar un poco más
                        stuck_counter += 1
                        if stuck_counter > 10:  # 15 segundos sin progreso
                            self.log("🚨 Atasco detectado en orden incompleta, forzando retorno")
                            try:
                                self.driver.get(URL_ORDENES)
                                stuck_counter = 0
                            except:
                                pass
                        time.sleep(1.5)

                # 2. SI ESTAMOS EN LA LISTA (AUTO)
                elif "fiatOrder" in url or "c2c-admin.binance.com/order" in url:
                    if self.is_paused:
                        time.sleep(1)
                        continue

                    self.status_lbl.configure(text="ESCANEANDO...", text_color="#2CC985")
                    stuck_counter = 0  # Reset counter when in list

                    try:
                        # Intentamos activar el filtro 'Pago pendiente' para que la lista muestre
                        # únicamente órdenes nuevas (con marca de tiempo).
                        try:
                            self.click_pago_pendiente()
                        except:
                            pass

                        # Usamos sleep breve aquí para no quemar CPU, la lista no necesita WebDriverWait estricto
                        time.sleep(1.5)
                        src = self.driver.page_source

                        # Buscar IDs de órdenes
                        ids_encontrados = re.findall(r'"orderNumber":"(\d{18,20})"', src)
                        if not ids_encontrados:
                            ids_encontrados = re.findall(r'orderNo=(\d{18,20})', src)

                        # FILTRO DE ORO: Solo entra si NO está en la memoria
                        nuevas = [x for x in dict.fromkeys(ids_encontrados) if x not in self.ordenes_procesadas]

                        # Logs de conteo para depuración
                        try:
                            total_found = len(ids_encontrados)
                            total_new = len(nuevas)
                            queue_len = len(self.pending_queue)
                            self.log(f"🔎 IDs encontrados: {total_found} | Nuevas: {total_new} | En cola: {queue_len}")
                        except: pass

                        if nuevas:
                            # Procesar órdenes en el orden en que llegan
                            for target in nuevas:
                                self.log(f"⚡ Procesando Orden: {target}")
                                try:
                                    # NUEVA INTERFAZ ADMIN: Intentar hacer clic en la orden
                                    if "c2c-admin.binance.com" in url:
                                        # Intentar hacer clic en el elemento de la orden
                                        if self.click_order_element(target):
                                            self.procesar_orden_actual(target)
                                        else:
                                            # Si no se puede hacer clic, intentar navegar por URL como fallback
                                            self.log(f"⚠️ No se pudo hacer clic en orden {target}, intentando URL directa...")
                                            self.driver.get(f"https://c2c.binance.com/es/fiatOrderDetail?orderNo={target}")
                                            self.procesar_orden_actual(target)
                                    else:
                                        # Interfaz antigua: navegar por URL
                                        self.driver.get(f"https://c2c.binance.com/es/fiatOrderDetail?orderNo={target}")
                                        # Procesar de forma síncrona para extraer y agregar al buffer
                                        self.procesar_orden_actual(target)
                                except Exception as ex:
                                    self.log(f"❌ Error al procesar orden {target}: {ex}")
                                finally:
                                    # Asegurar que siempre regresemos a la lista de órdenes
                                    try:
                                        self.driver.get(URL_ORDENES)
                                    except:
                                        pass
                            # Reaplicar el filtro 'Pago pendiente' después de procesar todas las órdenes
                            try:
                                self.click_pago_pendiente()
                            except:
                                pass
                        else:
                            pass
                    except Exception as e:
                        print(f"Error Scan: {e}")

                # 3. URL DESCONOCIDA - Forzar retorno a lista
                elif "binance.com" in url:
                    # Estamos en Binance pero no en una URL conocida, simplemente continuar escaneando
                    pass
                else:
                    self.log(f"⚠️ URL desconocida detectada: {url[:100]}...")
                    try:
                        self.driver.get(URL_ORDENES)
                        time.sleep(2)
                    except Exception as e:
                        self.log(f"❌ Error forzando retorno desde URL desconocida: {e}")

                time.sleep(1.5)

            except (WebDriverException, NoSuchWindowException):
                self.reset_estado_bot()
                break
            except Exception as e:
                self.log(f"❌ Error en bucle principal: {e}")
                time.sleep(2)

    def procesar_orden_actual(self, oid):
        import threading

        # Marcar que estamos procesando una orden para que las solicitudes de pausa
        # durante el procesamiento se apliquen solo al finalizarla.
        self.processing_order = True

        def timeout_handler():
            self.log(f"⏰ Timeout de 10 segundos alcanzado para orden {oid}, forzando retorno a lista.")
            try:
                self.driver.get(URL_ORDENES)
            except:
                pass

        # Iniciar timer de 10 segundos
        timer = threading.Timer(10.0, timeout_handler)
        timer.start()

        try:
            # === Espera dinámica y detección temprana de estados a ignorar ===
            # Si el sistema ya está pausado (aplicado), abortamos y volvemos a la lista
            try:
                if self.is_paused:
                    try:
                        self.driver.get(URL_ORDENES)
                    except: pass
                    return
            except: pass

            try:
                wait = WebDriverWait(self.driver, 20)
                wait.until(lambda d: "Pagarás" in d.find_element(By.TAG_NAME, "body").text or "Importe" in d.find_element(By.TAG_NAME, "body").text or "Total" in d.find_element(By.TAG_NAME, "body").text)
            except TimeoutException:
                self.log("⚠️ Tiempo de espera agotado, intentando leer igual...")

            # Leemos el body para detectar estados - PERO AHORA PROCESAMOS TODAS LAS ÓRDENES INCLUYENDO "A LIBERAR"
            try:
                body_text = self.driver.find_element(By.TAG_NAME, "body").text
            except:
                body_text = ""





            # Solo ahora registramos que estamos extrayendo datos para órdenes válidas
            self.log(f"🔥 Extrayendo datos: {oid}")

            # === NUEVA LÓGICA HÍBRIDA: API + SELENIUM ===
            datos = {}

            # PRIMERO: Intentar obtener datos del CHAT via API (más confiable)
            try:
                chat_texto = self.consultar_api_chat(oid)
                if chat_texto:
                    datos_api = self.extraer_info_api(chat_texto)
                    if datos_api:
                        self.log("📡 Datos obtenidos via API")
                        datos.update(datos_api)
            except Exception as e:
                self.log(f"⚠️ Error API chat: {e}")

            # SEGUNDO: Extraer datos de la página web (complementario)
            for intento in range(1, 4): # Intentos 1, 2 y 3
                datos_web = self.extraer_datos_full(self.driver)

                # Si encontramos el monto, asumimos que la carga fue exitosa
                if datos_web.get("monto"):
                    datos.update(datos_web)  # Combinar datos API + web
                    break

                # Si no, esperamos un poco antes de reintentar
                if intento < 3:
                    self.log(f"⏳ Intento {intento}/3: Datos web incompletos. Reintentando en 2s...")
                    time.sleep(2)
            # ==================================================

            # Validar MONTO (Crucial para saber que la orden cargó)
            if datos.get("monto"):
                oid_s = str(int(oid))

                # En ambos modos (automático y manual), agregar al buffer
                try:
                    self.pending_queue.append((datos, oid_s))
                    self.guardar_orden(oid_s)
                    self.last_order_time = time.time()
                    queue_len = len(self.pending_queue)
                    self.log(f"📋 Orden {oid_s} agregada a buffer (total: {queue_len}).")
                    if self.modo_automatico:
                        self.log(f"Reiniciando temporizador de {self.buffer_time}s.")
                except Exception as e:
                    self.log(f"❌ Error al agregar a cola: {e}")
                try: self.driver.get(URL_ORDENES)
                except: pass

                # En modo manual, mostrar que hay órdenes pendientes para envío manual
                if not self.modo_automatico:
                    self.lbl_alert.configure(text=f"BUFFER: {queue_len} órdenes pendientes", text_color="orange")
                    self.btn_send.configure(state="normal")
            else:
                self.log(f"❌ Se ignoró la orden {oid} tras 5 intentos fallidos (No cargó información).")


                # 1. Marcamos la orden como "procesada" para no volver a caer aquí
                self.guardar_orden(str(int(oid)))

                # 2. Forzamos recarga de la página para buscar la siguiente orden
                try: self.driver.get(URL_ORDENES)
                except: pass
                # ===================================================

        finally:
            # Cancelar el timer si terminó normalmente
            timer.cancel()
            # Siempre indicar que ya no estamos procesando la orden
            try:
                self.processing_order = False
            except: pass
            # Si el usuario solicitó pausa mientras procesábamos, aplicarla ahora
            try:
                self.apply_pending_pause_if_requested()
            except: pass

    # ================= EXTRACTOR FULL (MEJORADO) =================
    def extraer_datos_full(self, driver):
        try:
            body_elem = driver.find_element(By.TAG_NAME, "body")
            txt = body_elem.text
            lineas = txt.split('\n')
            datos = {}

            # 1. MONTO - Lógica blindada
            # Busca especificamente texto que tenga formato de dinero y esté cerca de claves como "Total"
            # Ojo: Evitamos capturar "15:00" del timer.

            # Intento A: Buscar con símbolo de moneda explicito (VES, Bs)
            match_monto_moneda = re.search(r'(?:Bs\.|VES|Bs)\s*([\d\.,]+)', txt)

            if match_monto_moneda:
                datos["monto"] = match_monto_moneda.group(1)
            else:
                # Intento B: Buscar después de palabras clave, filtrando números pequeños (timer)
                match_monto_generico = re.search(r'(?:Pagarás|Importe|Total)\s*[\n\r]*\s*([^\d\n]*)([\d\.,]+)', txt)
                if match_monto_generico:
                    posible_monto = match_monto_generico.group(2)
                    # Si el monto tiene punto o coma, o es mayor a 100, asumimos que es dinero y no minutos
                    if "," in posible_monto or "." in posible_monto or len(posible_monto) > 3:
                        datos["monto"] = posible_monto

            # 2. TASA (Busca "Precio")
            match_tasa = re.search(r'(?:Precio|Price)\s*[\n\r]*\s*[^\d]*([\d\.,]+)', txt)
            if match_tasa:
                datos["tasa"] = match_tasa.group(1)

            # 3. DATOS PERSONALES (Iteración inteligente)
            keys = {
                "banco": ["nombre del banco", "bank name"],
                "cedula": ["cédula", "id number", "identificación", "numero de cédula"],
                "telefono": ["celular", "mobile", "phone", "teléfono", "numero de celular"],
                "titular": ["nombre completo", "receiver name", "titular", "nombre completo del receptor"],
                "cuenta": ["número de cuenta", "account number"]
            }

            for i, l in enumerate(lineas):
                l_stripped = l.strip()
                l_low = l_stripped.lower()

                # A veces el dato está en la misma línea (ej: "Banco: Banesco")
                # A veces está en la siguiente línea

                val = ""
                # Chequeo linea siguiente
                if i+1 < len(lineas):
                    posible_val = lineas[i+1].strip()
                    # Evitamos que el valor sea otra etiqueta (ej: que tome "Cédula" como valor de "Banco")
                    es_etiqueta = any(k in posible_val.lower() for k in ["cédula", "precio", "monto", "celular", "teléfono", "número de cuenta", "nombre completo", "numero de", "nombre del"])
                    if not es_etiqueta:
                        val = posible_val

                for k, t in keys.items():
                    if k not in datos and any(x in l_low for x in t):
                        # Prioridad: Si hay ":" en la linea actual, intenta sacar dato de ahí
                        if ":" in l_stripped:
                            split_v = l_stripped.split(":", 1)[1].strip()
                            if len(split_v) > 2: # Si hay algo relevante
                                datos[k] = split_v
                            elif val: # Si no, usa la linea de abajo
                                datos[k] = val
                        elif val:
                            datos[k] = val

            return datos
        except Exception as e:
            print(f"Error extraccion: {e}")
            return {}

    def verificar_estado_orden_api(self, oid):
        """Verifica el estado de una orden usando API para mejor detección."""
        try:
            ordenes = self.consultar_api_ordenes()
            if ordenes:
                for ord in ordenes:
                    if str(ord.get("orderNumber")) == str(oid):
                        status = ord.get("orderStatus", "")
                        # Estados que indican que la orden ya no está pendiente
                        estados_invalidos = ["COMPLETED", "CANCELLED", "EXPIRED", "APPEALED"]
                        if status in estados_invalidos:
                            self.log(f"📊 Orden {oid} en estado: {status} (marcando como procesada)")
                            return False  # No procesar
                        elif status == "PROCESS":
                            return True  # Procesar
            return True  # Si no encontramos la orden, asumir que es válida
        except Exception as e:
            self.log(f"⚠️ Error verificando estado API: {e}")
            return True  # En caso de error, procesar igual

    # ================= FUNCIONES API DEL BOT QR =================
    def enviar_mensaje_api(self, texto, chat_id=None):
        """Envía mensaje a Telegram usando API."""
        destinos = [chat_id] if chat_id else self.grupos_alertas
        for cid in destinos:
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                              json={"chat_id": cid, "text": texto, "parse_mode": "HTML"})
            except: pass

    def enviar_foto_qr(self, ruta_imagen):
        """Envía la foto del QR directamente a tu chat privado."""
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(ruta_imagen, "rb") as img:
            try:
                self.log("📤 Enviando Captura QR a Telegram...")
                requests.post(url, data={"chat_id": ID_ADMIN, "caption": "🔑 <b>ACCIÓN REQUERIDA:</b> Escanea el QR si aparece en la imagen."}, files={"photo": img})
            except Exception as e:
                self.log(f"Error enviando foto: {e}")

    def obtener_cookies_con_qr(self):
        """Obtiene cookies usando QR login."""
        self.log("🔑 Iniciando Navegador para Login QR...")
        options = Options()
        options.add_argument(f"user-data-dir={CARPETA_PERFIL}")

        if MODO_SERVIDOR:
            self.log("   ⚙️ Modo Servidor (Headless) ACTIVADO")
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
        else:
            self.log("   ⚙️ Modo PC (Visible) ACTIVADO")

        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        # Usar directorio personalizado para ChromeDriver
        try:
            driver_path = ChromeDriverManager(path=DIRECTORIO_CHROMEDRIVER).install()
            driver_qr = webdriver.Chrome(service=Service(driver_path), options=options)
        except PermissionError as pe:
            self.log(f"❌ Error de permisos en ChromeDriver (QR): {pe}")
            self.log("💡 Sugerencia: Ejecuta el programa como administrador.")
            return None, None
        except Exception as e:
            self.log(f"❌ Error inicializando ChromeDriver (QR): {e}")
            return None, None

        try:
            driver_qr.get("https://accounts.binance.com/es/login")
            time.sleep(5)

            # Intentar cerrar cookies si estorban
            try:
                driver_qr.find_element(By.ID, "onetrust-accept-btn-handler").click()
                time.sleep(1)
            except: pass

            # Si estamos en login, intentamos mostrar el QR y TOMAMOS LA FOTO SÍ O SÍ
            if "login" in driver_qr.current_url:
                self.log("📸 Página de login detectada.")

                # Intentar cambiar a pestaña QR (Best Effort)
                try:
                    botones_qr = driver_qr.find_elements(By.XPATH, "//*[contains(@class, 'qr') or contains(@data-type, 'qr')]")
                    for btn in botones_qr:
                        try:
                            if btn.is_displayed():
                                btn.click()
                                self.log("   🖱️ Click intentado en botón QR")
                                time.sleep(2)
                                break
                        except: pass
                except: pass

                # --- MOMENTO CRÍTICO: FOTO DE PANTALLA COMPLETA ---
                archivo_qr = "pantalla_login_full.png"
                driver_qr.save_screenshot(archivo_qr)
                self.enviar_foto_qr(archivo_qr)

                self.log("⏳ Esperando que escanees el QR (Detectando redirección)...")

                # Esperar redirección (2 minutos máx)
                login_exitoso = False
                for i in range(40):
                    time.sleep(3)
                    if "login" not in driver_qr.current_url:
                        self.log("🎉 ¡Redirección detectada!")
                        login_exitoso = True
                        break
                    if i % 10 == 0: self.log(f"   ... esperando ({i*3}s)")

                if not login_exitoso:
                    self.log("❌ Tiempo agotado. No se detectó redirección.")
                    return None, None

            # Esperar carga final del dashboard
            time.sleep(5)
            self.log("✅ Sesión activa. Extrayendo cookies...")

            # Extraer Cookies
            selenium_cookies = driver_qr.get_cookies()
            cookies_dict = {c['name']: c['value'] for c in selenium_cookies}
            csrf = cookies_dict.get("csrftoken", "")

            return cookies_dict, csrf

        except Exception as e:
            self.log(f"❌ Error Selenium QR: {e}")
            return None, None
        finally:
            self.log("🔒 Cerrando navegador QR...")
            driver_qr.quit()

    def actualizar_sesion_api(self):
        """Actualiza la sesión API usando QR."""
        global SESSION_COOKIES, SESSION_CSRF, SESSION_HEADERS

        cookies, csrf = self.obtener_cookies_con_qr()

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
            test_ordenes = self.consultar_api_ordenes()
            if test_ordenes is not None:
                self.log("✅ Sesión API obtenida y válida.")
                return True
            else:
                self.log("❌ Sesión obtenida pero inválida. Cookies expiradas.")
                return False
        return False

    def consultar_api_ordenes(self):
        """Consulta órdenes usando API."""
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

    def consultar_api_chat(self, order_no):
        """Consulta chat de una orden usando API."""
        try:
            r = requests.post(API_CHAT, headers=SESSION_HEADERS, cookies=SESSION_COOKIES, json={
                "orderNumber": order_no, "page": 1, "rows": 20
            }, timeout=10)
            msgs = r.json().get("data", [])
            return " ".join([m.get("content", "") for m in msgs])
        except: return ""

    def extraer_info_api(self, texto_chat):
        """Extrae información del chat usando expresiones regulares."""
        try:
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
        except Exception as e:
            print(f"Error extraccion API: {e}")
            return {}

    def enviar_round_robin(self, datos, oid):
        # Cédula
        raw_ced = datos.get('cedula', '')
        ced_clean = raw_ced
        if raw_ced:
            c = re.sub(r'[^0-9VEJGPvejgp]', '', raw_ced).upper()
            if len(c) > 4: # Validación simple para no borrar si no parece cedula
                pref = c[0] if c[0] in 'VEJGP' else 'V'
                nums = c[1:] if c[0] in 'VEJGP' else c
                ced_clean = f"{pref}{nums}"
            else:
                ced_clean = raw_ced

        # Formato: punto miles y coma decimales (10.000,00)
        def formatear(v):
            if not v:
                return "0,00"
            raw = str(v)
            clean = re.sub(r'[^0-9\.,]', '', raw)
            try:
                if ',' in clean and '.' in clean:
                    # Determine which separator is thousands/decimal by position
                    if clean.find(',') < clean.find('.'):
                        # e.g. '9,564.96' -> comma thousands, dot decimal
                        clean = clean.replace(',', '')
                    else:
                        # e.g. '9.564,96' -> dot thousands, comma decimal
                        clean = clean.replace('.', '').replace(',', '.')
                elif ',' in clean:
                    parts = clean.split(',')
                    if len(parts[-1]) == 2:
                        # comma used as decimal
                        clean = clean.replace(',', '.')
                    else:
                        # comma as thousands
                        clean = clean.replace(',', '')
                elif '.' in clean:
                    parts = clean.split('.')
                    if len(parts[-1]) == 2:
                        # dot used as decimal (keep)
                        pass
                    else:
                        # dot as thousands
                        clean = clean.replace('.', '')

                val = float(clean)
                s = "{:,.2f}".format(val)
                # Convert en_US formatting (comma thousands, dot decimal)
                # to Venezuelan: dot thousands, comma decimals
                s = s.replace(',', 'X').replace('.', ',').replace('X', '.')
                return s
            except:
                # Fallback: return cleaned string as-is
                return clean

        monto_final = formatear(datos.get('monto', '0'))
        
        # Format tasa if available
        tasa_final = ""
        if datos.get('tasa'):
            tasa_final = formatear(datos.get('tasa', '0'))

        msg = f"<b>ORDEN:</b> <code>{oid}</code>\n"
        msg += f"<b>MONTO:</b> <code>{monto_final}</code>\n"
        if tasa_final:
            msg += f"<b>TASA:</b> <code>{tasa_final}</code>\n"
        msg += "------------------\n"
        if datos.get('banco'): msg += f"🏦 <code>{datos.get('banco')}</code>\n"
        msg += f"🆔 <code>{ced_clean}</code>\n"
        if datos.get('telefono'): msg += f"📱 <code>{datos.get('telefono')}</code>\n"
        if datos.get('cuenta'): msg += f"🔢 <code>{datos.get('cuenta')}</code>\n"
        if datos.get('titular'): msg += f"👤 <code>{datos.get('titular')}</code>"

        grupo = self.grupos_alertas[self.indice_grupo]
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                          data={'chat_id': grupo, 'text': msg, 'parse_mode': 'HTML'})
            self.log(f"📤 Enviado al Grupo {self.indice_grupo + 1}")
        except:
            self.log("❌ Error Telegram")

        self.indice_grupo = (self.indice_grupo + 1) % len(self.grupos_alertas)

    def bucle_deteccion_grupos(self):
        """Thread that periodically checks for new groups via getUpdates."""
        while self.bot_running:
            try:
                self.detect_new_groups()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                self.log(f"❌ Error in group detection loop: {e}")
                time.sleep(10)

    def enviar_manual(self):
        # Enviar manualmente todo el buffer en orden de llegada
        if self.pending_queue:
            self.log(f"🚀 Enviando buffer manualmente: {len(self.pending_queue)} órdenes en orden de llegada.")

            # Usar la cola directamente sin revertir
            orders_to_send = list(self.pending_queue)
            self.pending_queue.clear()  # Limpiar la cola original

            selected_groups_ids = self.selected_groups
            if not selected_groups_ids:
                selected_groups_ids = [0]
            selected_groups = [self.grupos_alertas[i] for i in selected_groups_ids]
            groups = len(selected_groups)

            if self.distribute:
                gi = self.indice_grupo % groups
                grupo = selected_groups[gi]
                self.indice_grupo = (self.indice_grupo + 1) % groups
            else:
                grupo = selected_groups[0]

            # Enviar todas las órdenes en el orden de llegada
            for idx, (datos, oid) in enumerate(orders_to_send):
                try:
                    self.enviar_a_grupo(grupo, datos, oid)
                    self.guardar_orden(oid)
                    try:
                        group_num = selected_groups_ids[gi] + 1 if self.distribute else self.grupos_alertas.index(grupo) + 1
                        self.log(f"({idx+1}/{len(orders_to_send)}) Enviado al Grupo {group_num}")
                    except: pass
                except:
                    try:
                        self.pending_queue.append((datos, oid))  # Reencolar si falla
                    except: pass

            self.log(f"✅ Buffer enviado manualmente: {len(orders_to_send)} órdenes enviadas.")
            self.lbl_alert.configure(text="BUFFER ENVIADO", text_color="green")
            self.btn_send.configure(state="disabled")
            self.driver.get(URL_ORDENES)
        else:
            self.log("⚠️ No hay órdenes en el buffer para enviar.")





if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()