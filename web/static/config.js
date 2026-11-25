'use strict';
// URL base de la API de diarización, sin barra final.
// Vacía: la página y la API comparten origen (python src/servidor.py o gunicorn).
// En Vercel, web/scripts/construir.mjs reescribe este archivo con API_BASE_URL.
window.VOCES_CONFIG = {API_BASE_URL: ''};
