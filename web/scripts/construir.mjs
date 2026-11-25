// Prepara web/dist/ para Vercel: copia la página estática y genera
// static/config.js con la URL de la API tomada de la variable API_BASE_URL.
//   API_BASE_URL=https://voces-api.onrender.com node scripts/construir.mjs
import {cpSync, mkdirSync, rmSync, writeFileSync} from 'node:fs';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const web = join(dirname(fileURLToPath(import.meta.url)), '..');
const destino = join(web, 'dist');
const fallar = mensaje => { console.error(`construir.mjs: ${mensaje}`); process.exit(1); };

const base = (process.env.API_BASE_URL || '').trim().replace(/\/+$/, '');
if (!base) fallar('define API_BASE_URL (por ejemplo, https://voces-api.onrender.com) en las variables de entorno del proyecto.');
let url;
try { url = new URL(base); } catch { fallar(`API_BASE_URL no es una URL válida: ${base}`); }
const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
// Una página HTTPS no puede llamar a una API HTTP (contenido mixto).
if (url.protocol !== 'https:' && !(local && url.protocol === 'http:')) fallar('API_BASE_URL debe usar https://.');
if (url.search || url.hash) fallar('API_BASE_URL no debe llevar parámetros ni fragmentos.');

rmSync(destino, {recursive: true, force: true});
mkdirSync(destino);
cpSync(join(web, 'index.html'), join(destino, 'index.html'));
cpSync(join(web, 'static'), join(destino, 'static'), {recursive: true});
writeFileSync(join(destino, 'static', 'config.js'),
  `'use strict';\n// Generado por scripts/construir.mjs\nwindow.VOCES_CONFIG = ${JSON.stringify({API_BASE_URL: base})};\n`);
console.log(`dist/ listo · API_BASE_URL=${base}`);
