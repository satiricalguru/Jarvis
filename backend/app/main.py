import asyncio
import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from .brain import get_models_for_provider, get_provider_health, resolve_chat
from .models import ApiKeysRequest, ChatRequest, ChatResponse, TTSRequest
from .telegram_bot import router as telegram_router
from .tools import dispatch_action
from .tts import get_jarvis_prefix_path, synthesize_speech_bytes
from .voice_engine import VOICES_DIR, generate_voice

load_dotenv()

app = FastAPI(title="Project JARVIS API")

# Register Telegram webhook router
app.include_router(telegram_router)


# ── CORS configuration ────────────────────────────────────────────────────────
_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _prune_audio_cache() -> None:
    """Retain only the last 25 audio files and delete generated files older than 30 minutes."""
    try:
        if not VOICES_DIR.exists():
            return
        files = sorted(
            [p for p in VOICES_DIR.iterdir() if p.is_file() and p.name != "jarvis.wav"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        now = time.time()
        for i, p in enumerate(files):
            if i >= 25 or (now - p.stat().st_mtime > 1800):
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception:
        pass



# ─── Health ──────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/health/providers")
async def provider_health():
    return await get_provider_health()


# ─── Models catalogue ────────────────────────────────────────────────────────

@app.get("/models/{provider}")
async def list_models(provider: str):
    valid = {"groq", "mistral", "openrouter", "ollama"}
    if provider not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{provider}'. Valid: {valid}")
    models = await get_models_for_provider(provider)
    return {"provider": provider, "models": models}


# ─── API-key management ──────────────────────────────────────────────────────

@app.post("/settings/keys")
async def update_keys(request: ApiKeysRequest):
    mapping = {
        "GROQ_API_KEY":       request.groq,
        "MISTRAL_API_KEY":    request.mistral,
        "OPENROUTER_API_KEY": request.openrouter,
        "HUGGINGFACE_TOKEN":  request.huggingface,
    }
    updated: list[str] = []
    env_path = Path(__file__).resolve().parent.parent / ".env"
    from dotenv import set_key
    for env_key, value in mapping.items():
        if value is not None and value.strip():
            val = value.strip()
            os.environ[env_key] = val
            set_key(str(env_path), env_key, val, quote_mode="never")
            updated.append(env_key)
    return {"updated": updated}


@app.get("/settings/keys/status")
async def keys_status():
    return {
        "groq":        bool(os.getenv("GROQ_API_KEY")),
        "mistral":     bool(os.getenv("MISTRAL_API_KEY")),
        "openrouter":  bool(os.getenv("OPENROUTER_API_KEY")),
        "huggingface": bool(os.getenv("HUGGINGFACE_TOKEN")),
    }


# ─── Chat ─────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # Run system-action dispatch BEFORE asking the LLM
    action_status = await dispatch_action(
        request.message,
        provider=request.provider or None,
        model=request.model or None,
    )

    try:
        reply, provider = await resolve_chat(
            request.message,
            provider=request.provider or None,
            model=request.model or None,
            history=request.history or [],
            action_result=action_status,
        )
    except Exception as chat_exc:
        # Graceful fallback: return a helpful response to the user instead of a 500 error
        reply = (
            f"Sir, I could not reach any configured AI provider ({chat_exc}). "
            "Please check your internet connection, verify your API keys in Settings, or start Ollama locally."
        )
        provider = "system-fallback"

    tts_provider: str | None = None
    audio_url: str | None    = None

    # Per-request unique filenames to avoid concurrent-request audio collisions
    req_id   = uuid.uuid4().hex[:8]
    wav_path = VOICES_DIR / f"output_{req_id}.wav"
    mp3_path = VOICES_DIR / f"fallback_{req_id}.mp3"

    # 1) Try pocket-tts (WAV, voice cloning or catalog voice)
    try:
        await asyncio.to_thread(generate_voice, reply, out_path=wav_path)
        tts_provider = "pocket-tts"
        audio_url    = f"/audio/{wav_path.name}"
    except Exception as pocket_exc:
        # 2) Fallback — synthesize_speech_bytes ("auto")
        try:
            fallback_bytes, fallback_provider = await synthesize_speech_bytes(reply, "auto")
            VOICES_DIR.mkdir(parents=True, exist_ok=True)

            if fallback_provider == "gtts":
                await asyncio.to_thread(mp3_path.write_bytes, fallback_bytes)
                tts_provider = "gtts"
                audio_url    = f"/audio/{mp3_path.name}"
            else:
                await asyncio.to_thread(wav_path.write_bytes, fallback_bytes)
                tts_provider = fallback_provider
                audio_url    = f"/audio/{wav_path.name}"

            action_status = action_status or f"pocket-tts failed ({pocket_exc}); using {fallback_provider}"
        except Exception as fallback_exc:
            audio_url     = None
            action_status = action_status or (
                f"pocket-tts: {pocket_exc}; all TTS fallbacks failed: {fallback_exc}"
            )

    # Prune old generated audio files in background
    asyncio.create_task(asyncio.to_thread(_prune_audio_cache))

    return ChatResponse(
        reply=reply,
        provider=provider,
        model=request.model,
        action_status=action_status,
        audio_url=audio_url,
        tts_provider=tts_provider,
    )



# ─── TTS ──────────────────────────────────────────────────────────────────────

@app.post("/tts")
async def tts(request: TTSRequest):
    try:
        audio_bytes, prov = await synthesize_speech_bytes(request.text, request.engine)
        media_type = "audio/mpeg" if prov == "gtts" else "audio/wav"
        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={"X-TTS-Provider": prov},
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"TTS synthesis failed: {exc}") from exc


@app.get("/tts/prefix")
async def tts_prefix():
    prefix_path = get_jarvis_prefix_path()
    if not prefix_path:
        raise HTTPException(status_code=404, detail="jarvis.wav not found")
    return FileResponse(prefix_path, media_type="audio/wav", filename="jarvis.wav")


@app.get("/tts/mode")
async def tts_mode():
    from .voice_engine import _HAS_CLONING, CATALOG_VOICE, get_reference_wav
    ref_wav = get_reference_wav()
    return {
        "voice_cloning_available": _HAS_CLONING,
        "reference_wav_exists":    ref_wav.exists(),
        "catalog_voice":           CATALOG_VOICE,
        "active_mode": (
            "voice-cloning"
            if (_HAS_CLONING and ref_wav.exists())
            else f"catalog:{CATALOG_VOICE}"
        ),
    }



# ─── Dynamic audio serving ───────────────────────────────────────────────────
# Serve any file from VOICES_DIR at /audio/{filename}

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve any generated audio file from the voices directory."""
    # Reject path traversal before any resolution
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    target = (VOICES_DIR / filename).resolve()
    voices_resolved = VOICES_DIR.resolve()
    # Strict containment check — is_relative_to() is the correct guard (Python 3.9+)
    if not target.is_relative_to(voices_resolved):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"{filename} not found")
    media_type = "audio/mpeg" if filename.endswith(".mp3") else "audio/wav"
    return FileResponse(target, media_type=media_type, filename=filename)
