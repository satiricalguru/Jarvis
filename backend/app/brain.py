import os
from typing import Any

import httpx

SYSTEM_PROMPT = (
    "You are JARVIS, a loyal, highly intelligent AI assistant running on the user's Mac. "
    "Address the user as 'Sir'. Be concise, witty, and proactive.\n\n"
    "You have real system capabilities. When the user asks you to perform any of the "
    "following actions, simply acknowledge that you are doing it — the backend will "
    "execute it automatically:\n"
    "  • Open any website or URL (e.g. 'open youtube.com', 'open github')\n"
    "  • Launch any macOS app (e.g. 'open Spotify', 'launch Terminal', 'start Chrome')\n"
    "  • Create files on the Desktop or any path (e.g. 'create file notes.txt')\n"
    "  • Create folders (e.g. 'make folder Projects on Desktop')\n"
    "  • Delete files or folders (e.g. 'delete file old_notes.txt')\n"
    "  • Write content into files (e.g. 'write \"hello\" to notes.txt')\n"
    "  • Read files (e.g. 'read file notes.txt')\n"
    "  • List directory contents (e.g. 'list Desktop', 'what's in Downloads')\n"
    "  • Take screenshots (e.g. 'take a screenshot')\n"
    "  • Get system info (e.g. 'check battery', 'show memory usage')\n\n"
    "When acknowledging an action, be brief: 'Right away, Sir.' or 'Done, Sir.' "
    "If the user asks a question, answer it. If they ask you to do something listed "
    "above, confirm you are doing it without lengthy explanations."
)

GENERATE_SYSTEM_PROMPT = (
    "You are a precise text generator. Your task is to generate only the content requested "
    "by the user. Do not include any greeting, intro, outro, conversational filler, or formatting/tags "
    "unless explicitly requested. Write the requested content directly."
)

PROVIDER_MODELS: dict[str, list[dict[str, Any]]] = {
    "groq": [
        {"id": "llama-3.1-8b-instant",             "name": "Llama 3.1 8B Instant",     "free": True},
        {"id": "llama-3.3-70b-versatile",           "name": "Llama 3.3 70B Versatile",  "free": True},
        {"id": "llama-3.1-70b-versatile",           "name": "Llama 3.1 70B",             "free": True},
        {"id": "mixtral-8x7b-32768",                "name": "Mixtral 8x7B",              "free": True},
        {"id": "gemma2-9b-it",                      "name": "Gemma 2 9B",                "free": True},
        {"id": "deepseek-r1-distill-llama-70b",     "name": "DeepSeek R1 Distill 70B",  "free": True},
        {"id": "meta-llama/llama-4-scout-17b-16e-instruct", "name": "Llama 4 Scout 17B","free": True},
        {"id": "meta-llama/llama-4-maverick-17b-128e-instruct","name": "Llama 4 Maverick","free": True},
        {"id": "compound-beta",                     "name": "Compound Beta",             "free": True},
    ],
    "mistral": [
        {"id": "open-mistral-7b",       "name": "Mistral 7B (Open)",    "free": True},
        {"id": "open-mixtral-8x7b",     "name": "Mixtral 8x7B (Open)",  "free": True},
        {"id": "open-mixtral-8x22b",    "name": "Mixtral 8x22B (Open)", "free": True},
        {"id": "mistral-small-latest",  "name": "Mistral Small",        "free": False},
        {"id": "mistral-medium-latest", "name": "Mistral Medium",       "free": False},
        {"id": "mistral-large-latest",  "name": "Mistral Large",        "free": False},
        {"id": "codestral-latest",      "name": "Codestral",            "free": False},
    ],
    "openrouter": [
        {"id": "meta-llama/llama-3.1-8b-instruct:free",         "name": "Llama 3.1 8B",   "free": True},
        {"id": "google/gemma-2-9b-it:free",                      "name": "Gemma 2 9B",     "free": True},
        {"id": "microsoft/phi-3-mini-128k-instruct:free",        "name": "Phi-3 Mini 128K","free": True},
        {"id": "qwen/qwen-2-7b-instruct:free",                   "name": "Qwen 2 7B",      "free": True},
        {"id": "mistralai/mistral-7b-instruct:free",             "name": "Mistral 7B",     "free": True},
        {"id": "anthropic/claude-3-haiku",                       "name": "Claude 3 Haiku", "free": False},
        {"id": "openai/gpt-4o-mini",                             "name": "GPT-4o Mini",    "free": False},
        {"id": "google/gemini-flash-1.5",                        "name": "Gemini Flash 1.5","free": False},
        {"id": "anthropic/claude-sonnet-4",                      "name": "Claude Sonnet 4","free": False},
    ],
    "ollama": [],
}

_PROVIDER_FN: dict = {}  # populated below after fn definitions

_FALLBACK_ORDER = ["groq", "mistral", "openrouter", "ollama"]


def _build_messages(
    message: str,
    history: list[dict[str, str]] | None,
    system_prompt: str = SYSTEM_PROMPT,
) -> list[dict[str, str]]:
    """Build the full messages array with optional prior turns."""
    msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if history:
        for turn in history[-20:]:   # keep last 20 turns to stay within token limits
            if turn.get("role") in {"user", "assistant"} and turn.get("content"):
                msgs.append({"role": turn["role"], "content": turn["content"]})
    msgs.append({"role": "user", "content": message})
    return msgs


async def ask_groq(
    message: str,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing")
    payload = {
        "model": model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": _build_messages(message, history, system_prompt),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload, headers=headers,
        )
        if resp.status_code in {429, 500, 502, 503, 504}:
            raise RuntimeError(f"Groq unavailable: {resp.status_code}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def ask_mistral(
    message: str,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is missing")
    payload = {
        "model": model or os.getenv("MISTRAL_MODEL", "open-mistral-7b"),
        "messages": _build_messages(message, history, system_prompt),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.mistral.ai/v1/chat/completions",
            json=payload, headers=headers,
        )
        if resp.status_code in {429, 500, 502, 503, 504}:
            raise RuntimeError(f"Mistral unavailable: {resp.status_code}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def ask_openrouter(
    message: str,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is missing")
    payload = {
        "model": model or os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free"),
        "messages": _build_messages(message, history, system_prompt),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload, headers=headers,
        )
        if resp.status_code in {429, 500, 502, 503, 504}:
            raise RuntimeError(f"OpenRouter unavailable: {resp.status_code}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def ask_ollama(
    message: str,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
    candidates = (
        [model] if model
        else [
            os.getenv("OLLAMA_MODEL", "llama3"),
            os.getenv("OLLAMA_SECOND_MODEL", "gemma2"),
        ]
    )
    async with httpx.AsyncClient(timeout=60) as client:
        for m in candidates:
            payload = {
                "model": m,
                "messages": _build_messages(message, history, system_prompt),
                "stream": False,
            }
            try:
                resp = await client.post("http://localhost:11434/api/chat", json=payload)
                resp.raise_for_status()
                return resp.json()["message"]["content"]
            except Exception:
                continue
    raise RuntimeError("No local Ollama model available")


_PROVIDER_FN = {
    "groq":        ask_groq,
    "mistral":     ask_mistral,
    "openrouter":  ask_openrouter,
    "ollama":      ask_ollama,
}


async def resolve_chat(
    message: str,
    provider: str | None = None,
    model: str | None = None,
    history: list[dict[str, str]] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> tuple[str, str]:
    if provider and provider in _PROVIDER_FN:
        reply = await _PROVIDER_FN[provider](message, model, history, system_prompt=system_prompt)
        return reply, provider

    last_exc: Exception = RuntimeError("No providers configured")
    for name in _FALLBACK_ORDER:
        fn = _PROVIDER_FN[name]
        try:
            reply = await fn(message, None, history, system_prompt=system_prompt)
            return reply, name
        except Exception as exc:
            last_exc = exc
    raise last_exc


# ── Model catalogue helpers ──────────────────────────────────

async def get_ollama_models() -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=4) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.is_success:
                return [
                    {"id": m["name"], "name": m["name"], "free": True}
                    for m in resp.json().get("models", [])
                ]
    except Exception:
        pass
    return []


async def get_models_for_provider(provider: str) -> list[dict[str, Any]]:
    if provider == "ollama":
        return await get_ollama_models()
    return PROVIDER_MODELS.get(provider, [])


# ── Health checks ─────────────────────────────────────────────

async def get_provider_health() -> dict[str, bool]:
    status: dict[str, bool] = {
        "groq": False, "mistral": False, "openrouter": False, "ollama": False,
    }
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {groq_key}"},
                )
                status["groq"] = r.is_success
        except Exception:
            pass

    mistral_key = os.getenv("MISTRAL_API_KEY")
    if mistral_key:
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.get(
                    "https://api.mistral.ai/v1/models",
                    headers={"Authorization": f"Bearer {mistral_key}"},
                )
                status["mistral"] = r.is_success
        except Exception:
            pass

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {openrouter_key}"},
                )
                status["openrouter"] = r.is_success
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=4) as c:
            r = await c.get("http://localhost:11434/api/tags")
            status["ollama"] = r.is_success
    except Exception:
        pass

    return status
