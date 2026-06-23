---
title: Telegram Stremio
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

<p align="center">
  <img src="https://iili.io/KhN0ztj.png" alt="Logo" width="400"/>
</p>

<p align="center">
  A powerful, self-hosted <b>Telegram Stremio Media Server</b> built with <b>FastAPI</b>, <b>MongoDB</b>, and <b>PyroFork</b> — seamlessly integrated with <b>Stremio</b> for automated media streaming and discovery.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/UV%20Package%20Manager-2B7A77?logo=uv&logoColor=white" alt="UV Package Manager" />
  <img src="https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/MongoDB-47A248?logo=mongodb&logoColor=white" alt="MongoDB" />
  <img src="https://img.shields.io/badge/PyroFork-EE3A3A?logo=python&logoColor=white" alt="PyroFork" />
  <img src="https://img.shields.io/badge/Stremio-8D3DAF?logo=stremio&logoColor=white" alt="Stremio" />
  <img src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/HF_Spaces-Deploy-yellow" alt="Hugging Face" />
</p>

---

## 🚀 Quick Start

### 1️⃣ Deploy on Hugging Face (free)

1. Fork this repo
2. Create a **Docker Space** on Hugging Face
3. Add these **Secrets** in Space Settings:

| Secret | Value |
|---|---|
| `API_ID` | From [my.telegram.org](https://my.telegram.org) |
| `API_HASH` | From my.telegram.org |
| `BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `HELPER_BOT_TOKEN` | Second bot from BotFather |
| `OWNER_ID` | Your Telegram user ID |
| `DATABASE` | `tracking_uri,storage_uri` (2 MongoDB URIs) |

4. Deploy — your server is live!

### 2️⃣ Add media sources

Send video files to your Telegram channel/group, then:

Open WebUI → Admin Tools → Scan

### 3️⃣ Install in Stremio

Open WebUI → Access → Copy manifest URL → Paste in Stremio

---

## 🧭 Quick Navigation

* [🚀 Introduction](#-introduction)
* [✨ Key Features](#-key-features)
* [⚙️ How It Works](#️-how-it-works)
* [🤖 Bot Commands](#-bot-commands)
* [🔧 Configuration Guide](#-configuration-guide)
* [💳 Subscription Management](#-subscription-management)
* [📺 Setting Up Stremio](#-setting-up-stremio)

---

## 🚀 Introduction

This project is a **next-generation Telegram Stremio Media Server** that allows you to **stream your Telegram files directly through Stremio**, without any third-party dependencies or file expiration issues. It's designed for **speed, scalability, and reliability**, making it ideal for both personal and community-based media hosting.

### ✨ Key Features

- ⚙️ **Multiple MongoDB Database Support**
- 📡 **Multiple Telegram Channel Support**
- ⚡ **Ultra-Fast Streaming Experience**
- 🔑 **Multi-Token Load Balancer**
- 🎬 **IMDb & TMDb Metadata Integration**
- 🧩 **Seamless Split File Streaming Support**
- 🎞️ **Play Multi-Part Videos as a Single Stream**
- ♾️ **Permanent Streaming Links (No Expiration)**
- 🧠 **Powerful Admin Dashboard**
- 💳 **Subscription & Premium Management**
- 🔐 **Advanced Access Control System**
- 📚 **Custom & Automatic Catalog Generation**
- 🖥️ **Web-Based Configuration Panel**
- 🌐 **Built-in Addon Proxy Support**
- 🔍 **Global Search Across Selected Channels**

---

## ⚙️ How It Works

This project acts as a **bridge between Telegram storage and Stremio streaming**, connecting **Telegram**, **FastAPI**, and **Stremio** to enable seamless movie and TV show streaming directly from Telegram files.

### Overview

When you **forward Telegram files** (movies or TV episodes) to your **AUTH CHANNEL**, the bot automatically:

1. 🗃️ **Stores** the `message_id` and `chat_id` in the database.
2. 🧠 **Processes** file captions to extract key metadata (title, year, quality, etc.).
3. 🌐 **Generates a streaming URL** through the **PyroFork** module — routed by **FastAPI**.
4. 🎞️ **Provides Stremio Addon APIs**:
   - `/catalog` → Lists available media
   - `/meta` → Shows detailed information for each item
   - `/stream` → Streams the file directly via Telegram

### Upload Guidelines

#### 🎥 For Movies

**Example Caption:**
```
Ghosted 2023 720p 10bit WEBRip [Org APTV Hindi AAC 2.0CH + English 6CH] x265 HEVC Msub ~ PSA.mkv
```

**Required Fields:** Name, Year, Quality (720p, 1080p, 2160p)

#### 📺 For TV Shows

**Example Caption:**
```
Harikatha.Sambhavami.Yuge.Yuge.S01E04.Dark.Hours.1080p.WEB-DL.DUAL.DDP5.1.Atmos.H.264-Spidey.mkv
```

**Required Fields:** Name, Season (S01), Episode (E04), Quality

---

## 🔧 Configuration

### Startup Configuration (config.env or HF Secrets)

| Variable | Description |
| :--- | :--- |
| **`API_ID`** | Telegram API ID from my.telegram.org |
| **`API_HASH`** | Telegram API Hash from my.telegram.org |
| **`BOT_TOKEN`** | Bot token from @BotFather |
| **`HELPER_BOT_TOKEN`** | Second bot token for streaming |
| **`OWNER_ID`** | Your Telegram user ID |
| **`DATABASE`** | MongoDB connection URI (tracking,storage) |
| **`PORT`** | Server port (7860 for HF Spaces) |

### Web Panel Configuration

Configure from `/admin/config` after startup:
- `BASE_URL`, `AUTH_CHANNEL`, `TMDB_API`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `REPLACE_MODE`, `HIDE_CATALOG`, `SUBSCRIPTION`
- Proxy settings, update repo, multi-token, etc.

---

## 🤖 Bot Commands

| Command | Description |
| :--- | :--- |
| **`/start`** | Returns your Addon URL for Stremio |
| **`/log`** | Sends the latest log file |
| **`/set`** | Manual uploads with IMDB URL |
| **`/restart`** | Restarts the bot |

---

## 📺 Setting up Stremio

1. Download Stremio from [stremio.com/downloads](https://www.stremio.com/downloads)
2. Sign in to your Stremio account
3. Add the addon using your Space URL: `https://your-space.hf.space/stremio/manifest.json`

---

## 📜 License

GPL-3.0
