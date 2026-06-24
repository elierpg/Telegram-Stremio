---
title: MyNuvios — Telegram Stremio
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# MyNuvios — Telegram Stremio

Servidor de medios que conecta Telegram con Stremio. Enviás archivos a un canal de Telegram y se convierten automáticamente en un addon de Stremio para streaming directo.

## Cómo funciona

1. Enviás archivos de video a un canal o grupo de Telegram.
2. El bot los procesa, extrae metadatos (nombre, año, calidad, temporada/episodio) y los guarda en MongoDB.
3. El addon de Stremio expone los archivos como catálogo con metadatos de TMDb/IMDb.
4. Reproducís directo desde Stremio sin descargar ni esperar.

## Características

- **Catálogos automáticos** — películas y series se organizan solos con metadata real.
- **Panel web** — dashboard, escaneo, configuración, gestión de usuarios y suscripciones.
- **Metadata con TMDb/IMDb** — portadas, sinopsis, año, reparto. Si falla, podés corregirlo manualmente.
- **Multi-token** — varios bots de Telegram rotan para evitar rate limits.
- **Archivos divididos** — reproducí archivos multiparte como un solo stream.
- **Múltiples bases de datos** — soporte para varias instancias de MongoDB.
- **Suscripciones y premium** — control de acceso por usuario con planes.
- **Proxy integrado** — el addon se sirve desde el mismo servidor.
- **Comandos de bot** — `/start`, `/set`, `/log`, `/restart`, `/scan`, `/rescan`.
- **Búsqueda global** — buscá contenido en todos los canales indexados.

## Stack

| | |
|---|---|
| Backend | FastAPI (Python) |
| Bot | PyroFork |
| Base de datos | MongoDB |
| Frontend | Jinja2 + vanilla JS |
| Paquetería | UV |
| Despliegue | Docker / Hugging Face Spaces |

## Despliegue rápido en Hugging Face

1. Creá un Docker Space en HF.
2. Agregá estos secretos:

| Secret | Descripción |
|---|---|
| `API_ID` | De my.telegram.org |
| `API_HASH` | De my.telegram.org |
| `BOT_TOKEN` | De @BotFather |
| `HELPER_BOT_TOKEN` | Segundo bot para streaming |
| `OWNER_ID` | Tu ID de Telegram |
| `DATABASE` | `tracking_uri,storage_uri` (2 URIs de MongoDB) |

3. Desplegá.
4. Entrá al panel web y configurá `BASE_URL`, `AUTH_CHANNEL` y `TMDB_API` en `/admin/config`.
5. En `/admin/tools` escaneá tus canales para indexar el contenido.
6. Copiá la URL del addon desde el panel y agregala en Stremio.

## Requisitos

- Python 3.11+
- MongoDB (2 instancias recomendadas: tracking + storage)
- Docker (para HF Spaces)
- 2 bots de Telegram (principal + helper para streaming)
- Canal de Telegram donde el bot sea admin

## Licencia

GPL-3.0
