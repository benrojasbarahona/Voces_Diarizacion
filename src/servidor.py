"""Servidor HTTP: API de diarización y, opcionalmente, la página web.

En local sirve la página y la API desde el mismo origen (python src/servidor.py).
En producción se ejecuta con gunicorn (gunicorn -c gunicorn.conf.py) y puede
atender a un frontend alojado en otro dominio si este figura en CORS_ORIGINS.
El análisis es el mismo que usa el menú de consola.
"""
import os
import re
from pathlib import Path
import tempfile
from threading import Lock

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from diarizacion import EXTENSIONES_AUDIO, ejecutar_diarizacion

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
load_dotenv(ROOT / '.env')


def _activado(valor):
    return str(valor).strip().lower() not in ('', '0', 'false', 'no')


def _origenes(valor):
    """CORS_ORIGINS: orígenes exactos separados por comas, o «*» para cualquiera."""
    return {origen.strip().rstrip('/') for origen in str(valor).split(',') if origen.strip()}


def crear_app(config=None):
    opciones = {'SERVIR_WEB': os.getenv('SERVIR_WEB', '1'),
                'CORS_ORIGINS': os.getenv('CORS_ORIGINS', ''), **(config or {})}
    servir_web = _activado(opciones['SERVIR_WEB'])
    app = Flask(__name__, static_folder=str(WEB / 'static') if servir_web else None,
                static_url_path='/static')
    limite_mb = int(os.getenv('MAX_AUDIO_MB', '200'))
    if limite_mb < 1:
        raise ValueError('MAX_AUDIO_MB debe ser mayor que cero.')
    app.config.update(MAX_CONTENT_LENGTH=limite_mb * 1024 * 1024,
                      MAX_AUDIO_MB=limite_mb)
    app.config.update(opciones)
    app.json.ensure_ascii = False
    # Un análisis a la vez por proceso: gunicorn.conf.py fija un único worker.
    bloqueo = Lock()

    @app.after_request
    def cors(respuesta):
        if not request.path.startswith('/api/'):
            return respuesta
        respuesta.vary.add('Origin')
        origen = request.headers.get('Origin', '').rstrip('/')
        permitidos = _origenes(app.config['CORS_ORIGINS'])
        if origen and ('*' in permitidos or origen in permitidos):
            respuesta.headers['Access-Control-Allow-Origin'] = origen
            respuesta.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            respuesta.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            respuesta.headers['Access-Control-Max-Age'] = '600'
        return respuesta

    if servir_web:
        @app.get('/')
        def inicio():
            return send_from_directory(WEB, 'index.html')

    @app.get('/api/salud')
    def salud():
        return jsonify(estado='ok')

    @app.get('/api/config')
    def configuracion():
        return jsonify(max_mb=app.config['MAX_AUDIO_MB'], formatos=sorted(EXTENSIONES_AUDIO),
                       analisis_en_curso=bloqueo.locked())

    @app.errorhandler(RequestEntityTooLarge)
    def demasiado_grande(_error):
        return jsonify(error=f"El archivo supera el límite de {app.config['MAX_AUDIO_MB']} MB."), 413

    @app.errorhandler(HTTPException)
    def error_http(exc):
        # La página espera JSON en cualquier respuesta de /api/ (404, 405...).
        if request.path.startswith('/api/'):
            return jsonify(error=exc.description), exc.code
        return exc

    @app.post('/api/diarizar')
    def diarizar():
        archivo = request.files.get('audio')
        if archivo is None or not archivo.filename:
            return jsonify(error='Selecciona un archivo de audio.'), 400
        nombre = archivo.filename.replace('\\', '/').rsplit('/', 1)[-1]
        extension = Path(nombre).suffix.lower()
        if extension not in EXTENSIONES_AUDIO:
            return jsonify(error='Formato no admitido. Selecciona un audio; los videos quedan fuera por ahora.'), 400
        cantidad = request.form.get('num_speakers', '')
        if cantidad and not re.fullmatch(r'[1-9][0-9]*', cantidad):
            return jsonify(error='La cantidad de hablantes debe ser un entero positivo.'), 400
        try:
            num_speakers = int(cantidad) if cantidad else None
        except ValueError:
            return jsonify(error='La cantidad de hablantes debe ser un entero positivo.'), 400
        if not bloqueo.acquire(blocking=False):
            return jsonify(error='Ya hay un análisis en curso. Espera a que termine e inténtalo nuevamente.'), 409
        try:
            # No usar el nombre enviado como ruta, ni escribir en data/.
            with tempfile.TemporaryDirectory(prefix='diarizacion_web_') as carpeta:
                ruta = Path(carpeta) / ('audio' + extension)
                archivo.save(ruta)
                if ruta.stat().st_size == 0:
                    return jsonify(error='El archivo está vacío.'), 400
                reporte = ejecutar_diarizacion(ruta, num_speakers=num_speakers)
                reporte['nombre_archivo'] = nombre
                return jsonify(reporte)
        except (ValueError, OSError) as exc:
            return jsonify(error=str(exc)), 422
        except Exception:
            app.logger.exception('Error durante la diarización')
            return jsonify(error='No se pudo completar el análisis. Revisa los registros del servidor e inténtalo nuevamente.'), 500
        finally:
            bloqueo.release()

    return app


if __name__ == '__main__':
    # Servidor de desarrollo. En producción: gunicorn -c gunicorn.conf.py
    crear_app().run(host=os.getenv('APP_HOST', '127.0.0.1'),
                    port=int(os.getenv('PORT') or os.getenv('APP_PORT', '8000')),
                    debug=False, threaded=True)
