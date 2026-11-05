import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path
import webview
import ctypes  # IMPORTANTE: Librería nativa para forzar el icono en Windows

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_URL = 'http://127.0.0.1:8000/'
PUBLIC_URL = 'https://smartstockchile.cl/'
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 8000
SPLASH_MIN_SECONDS = 1.5

def levantar_django():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
    sys.path.insert(0, str(BASE_DIR))
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py', 'runserver', f'{SERVER_HOST}:{SERVER_PORT}', '--noreload'])

def esperar_servidor(url, timeout=15):
    import urllib.request
    import urllib.error
    inicio = time.monotonic()
    while time.monotonic() - inicio < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.3)
    return False

def abrir_smartstock(ventana, url, iniciar_servidor):
    if not ventana.events.loaded.wait(20):
        logging.error('La pantalla de carga de SmartStock no se pudo mostrar.')
        return

    inicio = time.monotonic()
    if iniciar_servidor:
        threading.Thread(target=levantar_django, daemon=True).start()
        if not esperar_servidor(DEFAULT_URL):
            if not ventana.events.closed.is_set():
                ventana.evaluate_js(
                    "document.querySelector('.track').hidden = true;"
                    "document.querySelector('.status').textContent = "
                    "'El servidor local no respondió. Revisa la consola y vuelve a abrir SmartStock.';"
                )
            logging.error('El servidor local de SmartStock no respondió.')
            return

    espera = max(0, SPLASH_MIN_SECONDS - (time.monotonic() - inicio))
    if not ventana.events.closed.wait(espera):
        ventana.load_url(url)


def ocultar_revelado_nativo(window):
    window.load_css('#login-form #password::-ms-reveal { display: none; }')


def comprobar_webview2():
    import winreg

    ruta = r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for raiz, acceso in (
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_READ | winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_CURRENT_USER, winreg.KEY_READ),
    ):
        try:
            with winreg.OpenKey(raiz, ruta, 0, acceso) as clave:
                version, _ = winreg.QueryValueEx(clave, 'pv')
                if version and version != '0.0.0.0':
                    return
        except FileNotFoundError:
            continue
    raise RuntimeError('Instala Microsoft Edge WebView2 Runtime y vuelve a abrir SmartStock.')


def main():
    # --- TRUCO PARA WINDOWS ---
    # Desvincula la ventana de python.exe para que Windows acepte el icono personalizado
    if os.name == 'nt':
        try:
            myappid = 'duoc.smartstock.app.v1' # Identificador único arbitrario
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
    # --------------------------

    empaquetado = getattr(sys, 'frozen', False)
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default=PUBLIC_URL if empaquetado else DEFAULT_URL)
    parser.add_argument('--no-server', action='store_true')
    parser.add_argument('--width', type=int, default=1400)
    parser.add_argument('--height', type=int, default=900)
    args = parser.parse_args()

    if empaquetado and os.name == 'nt':
        comprobar_webview2()

    icon_path = BASE_DIR / 'icono.ico'
    pantalla_carga = (BASE_DIR / 'desktop_splash.html').read_text(encoding='utf-8')
    ventana = webview.create_window(
        title='SmartStock - Hub de Inventario',
        html=pantalla_carga,
        width=args.width,
        height=args.height,
        min_size=(1024, 700),
        resizable=True,
        confirm_close=True,
    )

    if os.name == 'nt':
        ventana.events.loaded += ocultar_revelado_nativo

    if empaquetado:
        webview.settings['ALLOW_DOWNLOADS'] = True

    webview.start(
        abrir_smartstock,
        args=(ventana, args.url, not empaquetado and not args.no_server),
        debug=False,
        gui='edgechromium' if empaquetado else None,
        icon=str(icon_path) if icon_path.is_file() else None
    )

if __name__ == '__main__':
    archivo_log = os.environ.get('SMARTSTOCK_DESKTOP_LOG')
    if archivo_log:
        logging.basicConfig(filename=archivo_log, level=logging.INFO, encoding='utf-8')
    try:
        main()
    except Exception as error:
        if not getattr(sys, 'frozen', False) or os.name != 'nt':
            raise
        if archivo_log:
            logging.exception('No se pudo abrir SmartStock')
        else:
            ctypes.windll.user32.MessageBoxW(
                None, f'No se pudo abrir SmartStock.\n\n{error}',
                'SmartStock', 0x10,
            )
        sys.exit(1)
