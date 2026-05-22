from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    # Conversation history: list of {"role": "user"|"assistant", "content": "..."}
    history: list[dict[str, str]] | None = None


class ChatResponse(BaseModel):
    reply: str
    provider: str
    model: str | None = None
    action_status: str | None = None
    audio_url: str | None = None
    tts_provider: str | None = None


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    engine: str = "auto"


class ApiKeysRequest(BaseModel):
    groq: str | None = None
    mistral: str | None = None
    openrouter: str | None = None
    huggingface: str | None = None
