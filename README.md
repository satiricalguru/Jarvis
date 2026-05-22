# Project J.A.R.V.I.S. 🤖

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Node.js-18%2B-green?logo=node.js&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/React-19-61dafb?logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/Three.js-holographic--ui-black?logo=three.js&logoColor=white" />
  <img src="https://img.shields.io/badge/license-MIT-yellow" />
</p>

<p align="center">
  A sci-fi AI assistant with a holographic React + Three.js interface and a FastAPI brain.<br/>
  Voice-activated · LLM-agnostic · Real macOS system actions · Zero-shot voice cloning
</p>

---

> **Screenshot / Demo**
> *(Add a screenshot or GIF here — drag an image into this file on GitHub)*

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Security Notice](#security-notice)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Manual Installation](#manual-installation)
  - [Backend](#1-backend-setup)
  - [Frontend](#2-frontend-setup)
  - [Voice Cloning](#zero-shot-voice-cloning-setup)
  - [Coqui TTS (optional)](#optional-coqui-tts-integration)
- [License](#license)

---

## Features

| Feature | Description |
|---|---|
| 🎙 Voice activation | Hold-to-talk or toggle mode, configurable hotkey |
| 🌐 Multi-provider LLM | Groq · Mistral · OpenRouter · Ollama (auto-fallback) |
| 🔊 Voice cloning | Pocket-TTS zero-shot cloning from a 5-second reference WAV |
| 🖥 macOS system actions | Open URLs/apps, create/read/write/delete files, screenshots, sysinfo |
| 📡 Telegram bot | Optional webhook integration |
| 🎨 Holographic HUD | Microphone-reactive Three.js blob, FFT bands, provider status |

---

## Prerequisites

- **OS**: macOS (system actions use `screencapture`, `pmset`, `open`)
- **Node.js** ≥ 18
- **Python** ≥ 3.10
- **API keys** (optional): Groq, OpenRouter, Mistral, or Hugging Face — or run fully locally with **Ollama**

---

## Security Notice

> [!WARNING]
> **Never commit `.env` files or hard-code API keys.**
> - All `.env` files and virtual environments are in `.gitignore`.
> - Manage keys at runtime via the **Settings → API Keys** tab in the frontend.

---

## Project Structure

```
Jarvisai/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, routes, CORS
│   │   ├── brain.py         # LLM provider logic + fallback chain
│   │   ├── tools.py         # macOS system-action dispatcher
│   │   ├── tts.py           # TTS synthesis (HuggingFace / Coqui / gTTS)
│   │   ├── voice_engine.py  # Pocket-TTS voice cloning engine
│   │   ├── telegram_bot.py  # Optional Telegram webhook
│   │   └── models.py        # Pydantic request/response models
│   ├── voices/              # Generated audio output (git-ignored)
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main application shell
│   │   ├── components/      # MicBlobScene, SettingsModal, TerminalLog
│   │   ├── hooks/           # useSpeechToText, useDubbedAudio
│   │   └── config.ts        # API_BASE configuration
│   └── package.json
└── start.sh                 # One-command launcher
```

---

## Quick Start

```bash
git clone https://github.com/satiricalguru/Jarvis.git
cd Jarvis

# Install backend deps
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env
cd ..

# Install frontend deps
cd frontend && npm install && cd ..

# Launch both servers
chmod +x start.sh && ./start.sh
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Manual Installation

### 1. Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in your keys
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev                 # runs at http://localhost:5173
```

### Zero-shot Voice Cloning Setup

1. Place a 5-second WAV sample of your target voice at `backend/voices/jarvis.wav`.
2. Add your `HUGGINGFACE_TOKEN` to `backend/.env` and accept the [pocket-tts model terms](https://huggingface.co/kyutai/pocket-tts).
3. Chat replies will automatically be dubbed in that voice.

### Optional: Coqui TTS Integration

```bash
cd backend && source .venv/bin/activate
pip install -r requirements-tts-coqui.txt
```

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.
