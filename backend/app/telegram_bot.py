import os

import httpx
from fastapi import APIRouter, HTTPException, Request

from .brain import resolve_chat
from .tools import dispatch_action

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def telegram_webhook(payload: Request):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN not configured")

    secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    if secret_token:
        header_secret = payload.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header_secret != secret_token:
            raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret token")

    body = await payload.json()
    message = body.get("message", {}).get("text", "")
    chat_id = body.get("message", {}).get("chat", {}).get("id")
    if not message or not chat_id:
        return {"ok": True}

    # Only allow executing host system actions if explicitly enabled for Telegram
    allow_remote_actions = os.getenv("ALLOW_REMOTE_SYSTEM_ACTIONS", "false").lower() in ("1", "true", "yes")
    action = None
    if allow_remote_actions:
        action = await dispatch_action(message)

    reply, provider = await resolve_chat(message, action_result=action)

    async with httpx.AsyncClient(timeout=20) as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"{reply}\n\n[{provider}] {action or ''}".strip(),
            },
        )
    return {"ok": True}

