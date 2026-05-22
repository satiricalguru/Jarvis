"""
voice_engine.py — Pocket-TTS voice synthesis with graceful cloning fallback.

Priority:
  1. Voice cloning  — needs gated kyutai/pocket-tts AND jarvis.wav reference
  2. Catalog voice  — uses 'marius' (deep male) from pocket-tts-without-voice-cloning

numpy and torch are imported lazily inside _audio_to_wav so that the rest of the
backend can start cleanly on machines where the heavy ML stack isn't installed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import login

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR      = Path(__file__).resolve().parent.parent
VOICES_DIR    = BASE_DIR / "voices"
REFERENCE_WAV = VOICES_DIR / "jarvis.wav"

# Best deep male catalog voice
CATALOG_VOICE = "marius"

_MODEL       = None   # cached TTSModel instance
_HAS_CLONING = False  # True only after we've verified cloning works at runtime


def _ensure_hf_token() -> str:
    token = os.getenv("HUGGINGFACE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("HUGGINGFACE_TOKEN is not set. Add it to backend/.env")
    return token


def _load_model():
    global _MODEL, _HAS_CLONING
    if _MODEL is not None:
        return _MODEL

    token = _ensure_hf_token()
    login(token=token, add_to_git_credential=False)

    try:
        from pocket_tts import TTSModel  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pocket-tts not installed") from exc

    logger.info("Loading pocket-tts model (first run downloads ~500 MB)…")
    _MODEL = TTSModel.load_model()

    # ── Real cloning probe ───────────────────────────────────────────────────
    # pocket-tts doesn't expose a boolean flag; we probe by trying to call
    # get_state_for_audio_prompt with an actual WAV file.  If it raises, the
    # gated weights aren't available and we fall back to catalog mode.
    if REFERENCE_WAV.exists():
        try:
            _MODEL.get_state_for_audio_prompt(str(REFERENCE_WAV))
            _HAS_CLONING = True
            logger.info("pocket-tts: voice-cloning probe PASSED ✓")
        except Exception as probe_exc:
            _HAS_CLONING = False
            logger.info(
                f"pocket-tts: voice-cloning probe FAILED ({probe_exc}). "
                "Accept gated terms at https://huggingface.co/kyutai/pocket-tts "
                f"to enable cloning. Using catalog voice '{CATALOG_VOICE}'."
            )
    else:
        _HAS_CLONING = False
        logger.info(
            f"No reference WAV at {REFERENCE_WAV}. "
            f"Using catalog voice '{CATALOG_VOICE}'."
        )

    return _MODEL


def _audio_to_wav(audio_tensor, sample_rate: int, out_path: Path) -> None:
    """Write a float tensor to out_path as 16-bit PCM WAV.

    numpy and torch are imported here so that importing voice_engine doesn't
    force the whole ML stack to load on machines without GPU/torch support.
    """
    import numpy as np  # lazy import
    import torch        # lazy import
    from scipy.io.wavfile import write as write_wav  # type: ignore

    arr = audio_tensor.detach().cpu()
    if isinstance(arr, torch.Tensor):
        arr = arr.numpy()
    arr = np.squeeze(arr)
    arr = np.clip(arr, -1.0, 1.0)
    pcm = (arr * 32767).astype(np.int16)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_wav(str(out_path), sample_rate, pcm)


def generate_voice(text: str, out_path: Path | None = None) -> Path:
    """
    Generate speech.  Writes to out_path (or VOICES_DIR/output.wav by default).

    Tries:
      1. Voice cloning from REFERENCE_WAV (needs gated model access)
      2. Catalog voice 'marius' (always works with non-gated model)
    """
    if out_path is None:
        out_path = VOICES_DIR / "output.wav"

    model     = _load_model()
    mode_used = "unknown"

    try:
        if _HAS_CLONING and REFERENCE_WAV.exists():
            state = model.get_state_for_audio_prompt(str(REFERENCE_WAV))
            audio = model.generate_audio(state, text)
            _audio_to_wav(audio, model.sample_rate, out_path)
            mode_used = "voice-cloning"
            logger.info("pocket-tts: voice cloning from jarvis.wav ✓")
        else:
            raise ValueError("cloning unavailable, using catalog voice")

    except Exception as cloning_exc:
        logger.info(
            f"pocket-tts: cloning skipped ({cloning_exc}), "
            f"falling back to catalog voice '{CATALOG_VOICE}'"
        )
        try:
            state = model.get_state_for_audio_prompt(CATALOG_VOICE)
            audio = model.generate_audio(state, text)
            _audio_to_wav(audio, model.sample_rate, out_path)
            mode_used = f"catalog:{CATALOG_VOICE}"
            logger.info(f"pocket-tts: catalog voice '{CATALOG_VOICE}' ✓")
        except Exception as catalog_exc:
            raise RuntimeError(
                f"pocket-tts failed entirely — cloning: {cloning_exc}; "
                f"catalog: {catalog_exc}"
            ) from catalog_exc

    if not out_path.exists() or out_path.stat().st_size < 100:
        raise RuntimeError(f"pocket-tts produced empty output (mode={mode_used})")

    return out_path
