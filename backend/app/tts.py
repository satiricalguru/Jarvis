import asyncio
import os
import tempfile
from pathlib import Path

import httpx

JARVIS_WAV_PATH = Path(__file__).resolve().parent.parent / "voices" / "jarvis.wav"
if not JARVIS_WAV_PATH.exists():
    JARVIS_WAV_PATH = Path(__file__).resolve().parent.parent / "assets" / "jarvis.wav"


def play_jarvis_prefix() -> str:
    if JARVIS_WAV_PATH.exists():
        return f"Prefix audio ready at {JARVIS_WAV_PATH}"
    hf_model = os.getenv("HF_TTS_MODEL", "kyutai/pocket-tts")
    has_hf_token = bool(os.getenv("HUGGINGFACE_TOKEN"))
    if has_hf_token:
        return f"Prefix missing; HF TTS model configured: {hf_model}"
    return "Prefix audio missing (expected backend/assets/jarvis.wav)"


def get_jarvis_prefix_path() -> Path | None:
    if JARVIS_WAV_PATH.exists():
        return JARVIS_WAV_PATH
    return None


async def synthesize_speech_bytes(text: str, engine: str = "auto") -> tuple[bytes, str]:
    requested = engine.lower().strip()
    if requested == "gtts":
        res = await asyncio.to_thread(_synthesize_with_gtts, text)
        return res, "gtts"
    if requested == "coqui":
        res = await asyncio.to_thread(_synthesize_with_coqui, text)
        return res, "coqui"
    if requested in {"hf", "huggingface"}:
        hf_token = os.getenv("HUGGINGFACE_TOKEN")
        hf_model = os.getenv("HF_TTS_MODEL", "kyutai/pocket-tts")
        if not hf_token:
            raise RuntimeError("HUGGINGFACE_TOKEN missing for hf engine")
        audio = await _synthesize_with_huggingface(text, hf_model, hf_token)
        return audio, "huggingface"

    hf_token = os.getenv("HUGGINGFACE_TOKEN")
    hf_model = os.getenv("HF_TTS_MODEL", "kyutai/pocket-tts")
    if hf_token:
        try:
            audio = await _synthesize_with_huggingface(text, hf_model, hf_token)
            return audio, "huggingface"
        except Exception:
            pass

    try:
        audio = await asyncio.to_thread(_synthesize_with_coqui, text)
        return audio, "coqui"
    except Exception:
        pass

    audio = await asyncio.to_thread(_synthesize_with_gtts, text)
    return audio, "gtts"



async def _synthesize_with_huggingface(text: str, model: str, token: str) -> bytes:
    # Keep this fast so we can fall back instead of hanging.
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.post(
            f"https://api-inference.huggingface.co/models/{model}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "audio/wav",
                "Content-Type": "application/json",
            },
            json={"inputs": text, "options": {"wait_for_model": False}},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "audio" not in content_type and len(response.content) < 2048:
            raise RuntimeError("HuggingFace did not return audio payload")
        return response.content


def _synthesize_with_coqui(text: str) -> bytes:
    try:
        from TTS.api import TTS  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Coqui TTS is not installed") from exc

    model_name = os.getenv("COQUI_TTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
    tts = TTS(model_name=model_name, progress_bar=False, gpu=False)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        if JARVIS_WAV_PATH.exists():
            tts.tts_to_file(text=text, speaker_wav=str(JARVIS_WAV_PATH), language="en", file_path=str(tmp_path))
        else:
            tts.tts_to_file(text=text, file_path=str(tmp_path))
        return tmp_path.read_bytes()
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _synthesize_with_gtts(text: str) -> bytes:
    from io import BytesIO

    try:
        from gtts import gTTS  # type: ignore
    except ImportError as exc:
        raise RuntimeError("gTTS is not installed") from exc

    stream = BytesIO()
    gTTS(text=text, lang="en").write_to_fp(stream)
    return stream.getvalue()
