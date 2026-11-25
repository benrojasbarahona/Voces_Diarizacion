# Despliegue en producción

La diarización necesita cómputo persistente, FFmpeg y varios cientos de MB de
dependencias (librosa, sherpa-onnx, scikit-learn, PyTorch para Resemblyzer).
Por eso se separa en dos piezas:

| Pieza | Dónde | Qué contiene |
|---|---|---|
| **API** | Render o Railway (contenedor Docker) | `src/`, `gunicorn.conf.py`, modelo ERes2Net y FFmpeg |
| **Página** | Vercel (sitio estático) | `web/index.html` y `web/static/` |

```text
Navegador ──(HTML/JS)──► Vercel
    │
    └──(POST /api/diarizar, multipart, CORS)──► Render/Railway ─► gunicorn ─► Flask ─► diarización
```

## 0. Opción gratuita recomendada: Hugging Face Spaces

Un Space Docker gratuito («CPU basic») ofrece 2 vCPU y 16 GB de RAM sin
tarjeta, y sirve la página y la API en la misma URL. Se duerme tras 48 h sin
visitas y despierta al abrir la página (tarda uno o dos minutos).
Alternativas gratuitas peores para este caso: Render Free (512 MB y 0,1 CPU,
alcanza solo para audios de pocos minutos y muy lento), Railway (sin plan
gratuito permanente).

1. En huggingface.co: *New Space* → SDK **Docker** → plantilla *Blank* →
   hardware **CPU basic (free)** → visibilidad **Public** (un Space privado
   exige iniciar sesión a cada visitante).
2. *Settings → Access Tokens* → token con permiso **Write**.
3. En GitHub, *Settings → Secrets and variables → Actions*:
   secreto `HF_TOKEN` (el token) y variable `HF_SPACE` (`<usuario>/<space>`).
4. Haz merge a `main`. `.github/workflows/huggingface.yml` copia al Space solo
   `Dockerfile`, `src/`, `web/`, los requerimientos y
   `despliegue/huggingface/README.md` (sin `data/`, `evaluacion/` ni `tests/`),
   y Hugging Face construye la imagen. Se repite en cada push a `main`; también
   puede lanzarse a mano desde *Actions → Publicar en Hugging Face → Run workflow*.
5. Abre `https://<usuario>-<space>.hf.space`: es la app completa. Comparte esa
   URL directa (dentro de la página del Space va en un iframe y el micrófono
   puede quedar bloqueado).

Vercel es opcional: si quieres mantenerlo (también gratis), usa
`API_BASE_URL=https://<usuario>-<space>.hf.space` en Vercel y, en *Settings →
Variables* del Space, `CORS_ORIGINS=https://<tu-proyecto>.vercel.app`.

## Arquitectura separada (Vercel + Render/Railway)

El audio se envía directamente del navegador a la API: no pasa por Vercel, cuyas
funciones limitan el tamaño del cuerpo y la duración de cada petición. La
reproducción por tramos sigue usando la copia local del archivo en el navegador.

## API

| Método y ruta | Uso |
|---|---|
| `POST /api/diarizar` | `multipart/form-data` con `audio` y `num_speakers` opcional. Devuelve el reporte JSON. |
| `GET /api/config` | Límite en MB, formatos admitidos y si hay un análisis en curso. La página lo consulta al cargar (y así despierta un servicio en reposo). |
| `GET /api/salud` | `{"estado": "ok"}` para las comprobaciones de salud. |

Errores siempre en JSON (`{"error": "..."}`): 400 validación, 409 análisis en
curso, 413 archivo demasiado grande, 422 audio ilegible, 500 error interno.

## 1. Backend (Docker)

La imagen (`Dockerfile`) instala FFmpeg, PyTorch solo CPU y las dependencias de
`requerimientos-produccion.txt`, descarga y verifica el modelo ERes2Net durante
la construcción y arranca `gunicorn -c gunicorn.conf.py` escuchando en `$PORT`.
Corre con un usuario sin privilegios.

`gunicorn.conf.py` usa **un único proceso con 4 hilos**: el servidor admite un
análisis a la vez (los demás reciben 409) y cada proceso adicional duplicaría el
modelo y el audio en memoria. No subas `workers`; escala con más instancias.

### Render

1. *New → Blueprint* y elige este repositorio (usa `render.yaml`), o *New → Web
   Service → Docker*.
2. Plan con **2 GB de RAM o más** (`standard`). Un audio de 13,5 min alcanzó
   ~860 MB de memoria; el consumo crece con la duración.
3. Variables: `CORS_ORIGINS=https://<tu-proyecto>.vercel.app`.
4. Health check: `/api/salud`.

### Railway

1. *New Project → Deploy from GitHub repo*. Detecta el `Dockerfile`;
   `railway.json` fija el health check.
2. Variables: `CORS_ORIGINS=https://<tu-proyecto>.vercel.app`.
3. *Settings → Networking → Generate Domain*. Railway asigna `PORT`.

### Variables de entorno del backend

| Variable | Valor en producción | Descripción |
|---|---|---|
| `PORT` | lo asigna la plataforma | Puerto de gunicorn (8000 si falta). |
| `CORS_ORIGINS` | `https://voces.vercel.app` | Orígenes autorizados, separados por comas, sin barra final. `*` autoriza cualquiera. |
| `MAX_AUDIO_MB` | `100` | Límite de carga. |
| `SERVIR_WEB` | `1` (imagen) | `1` sirve también la página en `/`; `0` deja solo la API. |
| `GUNICORN_THREADS` | `4` | Hilos del único proceso. |
| `GUNICORN_TIMEOUT` | `900` | Segundos. |

### Prueba local de la imagen

```bash
docker build -t voces-api .
docker run --rm -p 8000:8000 -e CORS_ORIGINS=http://localhost:5050 voces-api
curl http://localhost:8000/api/salud
curl -F "audio=@data/audio1.wav" http://localhost:8000/api/diarizar
```

## 2. Frontend (Vercel)

1. *Add New → Project*, importa el repositorio.
2. Root Directory: déjalo vacío (raíz del repositorio, usa `vercel.json`) o
   pon `web` (usa `web/vercel.json`). Ambos construyen con
   `scripts/construir.mjs` y publican `web/dist/`. No configures *Build
   Command* ni *Output Directory* en el panel: los toma de esos archivos.
3. Variable de entorno **`API_BASE_URL=https://<tu-api>.onrender.com`** (o el
   dominio de Railway), sin barra final, para Production y Preview.
4. Despliega y añade el dominio resultante a `CORS_ORIGINS` del backend.
5. El dominio de producción (`<proyecto>.vercel.app`) sirve la rama `main`;
   las ramas y los PR se publican en URL de *preview*.

`scripts/construir.mjs` copia la página a `dist/` y escribe
`static/config.js` con `API_BASE_URL`. Falla si la variable falta o no usa
`https://` (una página HTTPS no puede llamar a una API HTTP). Cambiar
`API_BASE_URL` exige volver a desplegar. Las URL de *preview* de Vercel cambian
en cada despliegue: agrégalas a `CORS_ORIGINS` solo si las necesitas.

Prueba local del resultado:

```bash
cd web && API_BASE_URL=http://127.0.0.1:8000 node scripts/construir.mjs
```

```bash
cd web/dist && python3 -m http.server 5050
```

## Modo unificado (sin Vercel)

Con `SERVIR_WEB=1` el mismo contenedor sirve la página en `/` y la API en
`/api/`, en el mismo origen: no hace falta `CORS_ORIGINS` ni `API_BASE_URL`.
Es lo más simple si no necesitas Vercel.

## Qué queda fuera de la imagen

`.dockerignore` excluye `data/` (125 MB de audios), `evaluacion/`, `tests/`,
`modelos/` (se descarga y verifica en la construcción), `Tiempo_audios.xlsx`,
`.env`, `.git` y los archivos de Vercel. En Vercel solo se publica `web/dist/`.

## Validación tras desplegar

1. `curl https://<api>/api/salud` → `{"estado":"ok"}`.
2. Petición previa de CORS desde el dominio de Vercel:
   `curl -i -X OPTIONS -H "Origin: https://<front>.vercel.app" -H "Access-Control-Request-Method: POST" https://<api>/api/diarizar`
   → `Access-Control-Allow-Origin` con ese dominio.
3. En la página: la insignia dice «Procesamiento en servidor», el límite «Hasta N
   MB» coincide con `MAX_AUDIO_MB`, y la pestaña Red muestra
   `GET https://<api>/api/config` con 200.
4. Sube un WAV corto, un M4A y un OGG (comprueba FFmpeg) y reproduce un turno
   con ▶.
5. Graba desde el micrófono (requiere HTTPS, que Vercel ya da).
6. Lanza dos análisis a la vez: el segundo debe responder 409.
7. Sube un archivo mayor que el límite: debe mostrar el error 413.
8. Analiza el audio más largo que esperas recibir y vigila la memoria y el
   tiempo en el panel de la plataforma.

## Límites conocidos

- Un análisis a la vez por instancia; el resto recibe 409.
- La petición permanece abierta durante todo el análisis (13,5 min de audio
  tardaron ~80 s con 2 hilos de ERes2Net). Render permite peticiones largas;
  Railway corta las HTTP a los 15 min. Para audios muy largos, el siguiente paso
  sería una cola de trabajos (POST que devuelve un id y consulta del estado).
- `MAX_AUDIO_MB` limita el tamaño, no la duración: un OGG o MP3 comprimido de
  100 MB puede durar horas y agotar la memoria.
- La API no tiene autenticación: cualquiera que conozca la URL puede enviarle
  audios. CORS solo impide que otras páginas lean las respuestas.
