import asyncio
from dataclasses import dataclass

import httpx

from medical_rag.config import Settings


class OllamaError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OllamaUnavailable(OllamaError):
    def __init__(self) -> None:
        super().__init__("ollama_unreachable")


class OllamaTimeout(OllamaError):
    def __init__(self) -> None:
        super().__init__("ollama_timeout")


class OllamaHTTPError(OllamaError):
    def __init__(self, status: int) -> None:
        super().__init__(f"ollama_http_{status}")
        self.status = status


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    num_ctx: int
    eval_count: int
    eval_duration_ns: int
    total_duration_ns: int
    done_reason: str = ""
    load_duration_ns: int = 0
    prompt_eval_count: int = 0
    prompt_eval_duration_ns: int = 0


class OllamaClient:
    """İnce HTTP istemcisi. Zaman aşımı ve num_ctx çağrı gövdesinde açıktır.

    Kilit, aynı anda ikinci üretimin KV önbelleğini ikiye katlamasını engeller.
    """

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._lock = asyncio.Lock()

    async def health(self) -> bool:
        url = self._settings.ollama_base_url.rstrip("/") + "/api/tags"
        try:
            response = await self._http.get(url, timeout=self._settings.health_timeout_seconds)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        num_predict: int | None = None,
    ) -> Completion:
        async with self._lock:
            return await self._chat_unlocked(messages, num_predict)

    async def _chat_unlocked(
        self,
        messages: list[dict[str, str]],
        num_predict: int | None,
    ) -> Completion:
        settings = self._settings
        payload = {
            "model": settings.model,
            "messages": messages,
            "stream": False,
            "think": settings.think,
            "keep_alive": settings.keep_alive,
            "options": {
                "num_ctx": settings.num_ctx,
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "top_k": settings.top_k,
                "num_predict": settings.num_predict if num_predict is None else num_predict,
            },
        }
        url = settings.ollama_base_url.rstrip("/") + "/api/chat"
        try:
            response = await self._http.post(
                url,
                json=payload,
                timeout=settings.request_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise OllamaTimeout from exc
        except httpx.HTTPError as exc:
            raise OllamaUnavailable from exc
        if response.status_code >= 400:
            raise OllamaHTTPError(response.status_code)
        body = response.json()
        message = body.get("message") or {}
        return Completion(
            text=str(message.get("content") or ""),
            model=str(body.get("model") or settings.model),
            num_ctx=settings.num_ctx,
            eval_count=int(body.get("eval_count") or 0),
            eval_duration_ns=int(body.get("eval_duration") or 0),
            total_duration_ns=int(body.get("total_duration") or 0),
            done_reason=str(body.get("done_reason") or ""),
            load_duration_ns=int(body.get("load_duration") or 0),
            prompt_eval_count=int(body.get("prompt_eval_count") or 0),
            prompt_eval_duration_ns=int(body.get("prompt_eval_duration") or 0),
        )
