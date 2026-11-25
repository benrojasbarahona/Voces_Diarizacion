"""Configuración de producción: gunicorn -c gunicorn.conf.py

Un único proceso con varios hilos. El análisis bloquea un hilo durante
minutos; los demás atienden /api/salud, /api/config y las respuestas 409.
"""
import os
from pathlib import Path

pythonpath = str(Path(__file__).resolve().parent / 'src')
wsgi_app = 'servidor:crear_app()'
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# No usar más workers: el bloqueo de un análisis a la vez es por proceso y
# cada proceso cargaría su propia copia del modelo y del audio en memoria.
workers = 1
worker_class = 'gthread'
threads = int(os.getenv('GUNICORN_THREADS', '4'))
# Margen para audios largos (con gthread no suele activarse, pero se mantiene alto).
timeout = int(os.getenv('GUNICORN_TIMEOUT', '900'))
graceful_timeout = 60
keepalive = 5

# El proxy de Render/Railway termina TLS delante del contenedor.
forwarded_allow_ips = '*'
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('LOG_LEVEL', 'info')
if Path('/dev/shm').is_dir():
    worker_tmp_dir = '/dev/shm'
