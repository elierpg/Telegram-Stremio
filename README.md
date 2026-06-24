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

Esto no es otro fork genérico de Telegram-Stremio. La mayoría de los repositorios que ves por GitHub son copias casi idénticas del proyecto base con cambios mínimos. Este no es el caso.

**MyNuvios** arrancó desde ese mismo origen, pero hoy es un proyecto diferente: reescrito, extendido y adaptado para uso real con administración completa desde el navegador, sin depender de comandos de bot para tareas críticas.

## ¿Qué lo hace distinto?

### WebUI como centro de control

El proyecto original depende casi enteramente de comandos de bot para administrar el servidor. MyNuvios tiene un panel web completo:

- **Escaneo y re-escaneo** desde la web, con progreso en tiempo real.
- **Revisión de archivos fallidos** con interfaz para corregir metadatos manualmente, buscar en TMDb/IMDb, y re-indexar — todo desde el navegador.
- **Panel de herramientas**: verificación de base de datos, limpieza de enlaces muertos, estado del sistema.
- **Configuración** en vivo desde el panel, sin reiniciar el servidor.
- **Gestión de suscripciones y premium** por usuario.
- **Dashboard** con estadísticas de almacenamiento, bases de datos, y actividad.

### No necesitas ser admin de Telegram para usarlo

Mientras el proyecto original asume que operás todo desde comandos de bot, acá podés tener usuarios con suscripciones que acceden solo por web. Ideal si querés compartir tu servidor con otras personas sin darles acceso a tu bot.

### Streaming más robusto

- **Multi-token load balancer**: varios tokens de Telegram rotan para evitar rate limits y caídas por sesión expirada.
- **Soporte para archivos divididos**: reproducí archivos multiparte (`.001`, `.002`, etc.) como un solo stream continuo.
- **Links permanentes**: no expiran, no dependen de que el bot esté activo.
- **Proxy integrado**: el addon de Stremio puede servirse a través del mismo servidor.

### Base de datos flexible

Soporte para **múltiples bases de datos MongoDB** simultáneas — podés separar tracking de storage, o distribuir medios entre varias instancias.

### Metadata real

Usa **guessit** + **TMDb API** para identificar contenido real, no solo el nombre del archivo. Si falla, podés corregirlo manualmente desde el panel de revisión. Incluye soporte para caracteres acentuados (series en español como "Aída" se parsean correctamente).

## Stack

- **FastAPI** — backend web
- **PyroFork** — cliente Telegram
- **MongoDB** — base de datos
- **Jinja2** — templates del panel web
- **UV** — package manager (más rápido que pip)
- **Docker** — despliegue

## Despliegue

Creado para correr en **Hugging Face Spaces** (Docker), pero funciona en cualquier VPS con Docker.

Agregá estos secretos en HF Spaces:

| Secret | Descripción |
|---|---|
| `API_ID` | De my.telegram.org |
| `API_HASH` | De my.telegram.org |
| `BOT_TOKEN` | De @BotFather |
| `HELPER_BOT_TOKEN` | Segundo bot para streaming |
| `OWNER_ID` | Tu ID de Telegram |
| `DATABASE` | `tracking_uri,storage_uri` (2 URIs de MongoDB) |

Después de desplegar, configura `BASE_URL`, `AUTH_CHANNEL` y `TMDB_API` desde el panel web en `/admin/config`.
