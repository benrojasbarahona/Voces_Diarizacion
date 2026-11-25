# syntax=docker/dockerfile:1
# Backend de diarización (Flask + gunicorn + FFmpeg) para Render, Railway o
# cualquier servicio de contenedores. Escucha en $PORT (8000 por defecto).

# ---------- Etapa de construcción: compila webrtcvad e instala dependencias ----------
FROM python:3.12-slim AS build
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
# PyTorch (lo pide Resemblyzer) en su versión solo CPU: evita varios GB de CUDA.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch
COPY requerimientos.txt requerimientos-produccion.txt ./
RUN pip install -r requerimientos-produccion.txt

# ---------- Imagen final ----------
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NUMBA_CACHE_DIR=/tmp/numba_cache \
    PORT=8000 \
    SERVIR_WEB=0 \
    MAX_AUDIO_MB=100
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY gunicorn.conf.py ./
COPY src/ src/
COPY web/index.html web/
COPY web/static/ web/static/
# Descarga y verifica (SHA-256) el modelo ERes2Net al construir, no en la primera petición.
RUN python -c "import sys; sys.path.insert(0, 'src'); from modelo_voz import obtener_modelo; print(obtener_modelo())"

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/salud' % os.environ.get('PORT', '8000'), timeout=4)" || exit 1
CMD ["gunicorn", "-c", "gunicorn.conf.py"]
