"""عميل LLM متوافق مع OpenAI API (Groq / Gemini / OpenRouter / أي مزوّد آخر) مع تبديل تلقائي عند الفشل."""
from __future__ import annotations

import asyncio
import logging
import re
import time

import httpx

from .config import Provider

log = logging.getLogger(__name__)
_THINK = re.compile(r"<think>.*?</think>", re.S)


class LLMUnavailable(Exception):
    pass


class LLM:
    def __init__(self, providers: tuple[Provider, ...], guard_models: tuple[str, ...]):
        self.providers = providers
        self.guard_models = guard_models
        self._cool: dict[tuple[str, str], float] = {}
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10))

    async def close(self):
        await self._client.aclose()

    def _candidates(self, guard: bool) -> list[tuple[Provider, str]]:
        if guard:
            c = [(self.providers[0], m) for m in self.guard_models]
            c += [(p, p.models[-1]) for p in self.providers[1:]]
            return c
        return [(p, m) for p in self.providers for m in p.models]

    async def chat(
        self, messages: list[dict[str, str]], *, temperature: float = 0.3,
        max_tokens: int = 700, guard: bool = False,
    ) -> str:
        now = time.time()
        cands = self._candidates(guard)
        ready = [c for c in cands if self._cool.get((c[0].name, c[1]), 0) <= now] or cands
        last_err = "no providers"
        for prov, model in ready:
            try:
                r = await self._client.post(
                    f"{prov.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {prov.api_key}"},
                    json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
                )
                if r.status_code == 429:
                    wait = float(r.headers.get("retry-after", "30") or 30)
                    self._cool[(prov.name, model)] = time.time() + min(max(wait, 5), 120)
                    last_err = f"429 {prov.name}/{model}"
                    continue
                if r.status_code >= 400:
                    last_err = f"{r.status_code} {prov.name}/{model}: {r.text[:150]}"
                    log.warning("LLM error %s", last_err)
                    if r.status_code in (401, 403, 404):
                        self._cool[(prov.name, model)] = time.time() + 600
                    continue
                text = r.json()["choices"][0]["message"]["content"] or ""
                text = _THINK.sub("", text).strip()
                if text:
                    return text
                last_err = f"empty {prov.name}/{model}"
            except (httpx.HTTPError, KeyError, ValueError, IndexError) as e:
                last_err = f"{type(e).__name__} {prov.name}/{model}"
                log.warning("LLM exception %s", last_err)
                await asyncio.sleep(0.3)
        raise LLMUnavailable(last_err)
