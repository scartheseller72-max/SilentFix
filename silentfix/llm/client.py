from __future__ import annotations
import typing as t
import json
from silentfix.config import get_config


class LLMClient:
    def __init__(self, backend: str | None = None, model: str | None = None):
        cfg = get_config()
        self.backend = backend or cfg.llm_backend
        self.model = model or cfg.llm_model

    def complete(self, prompt: str, system: str = "", max_tokens: int = 2048, json_mode: bool = False) -> str:
        cfg = get_config()
        if self.backend == "openai":
            return self._openai_complete(prompt, system, max_tokens, json_mode)
        elif self.backend == "ollama":
            return self._ollama_complete(prompt, system, max_tokens, json_mode)
        elif self.backend == "mock":
            return json.dumps({"error": "mock mode"}) if json_mode else ""
        return self._openai_complete(prompt, system, max_tokens, json_mode)

    def _openai_complete(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str:
        cfg = get_config()
        try:
            from openai import OpenAI
            client = OpenAI(api_key=cfg.openai_api_key)
            kwargs = {
                "model": cfg.openai_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.1,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as e:
            return json.dumps({"error": str(e)}) if json_mode else ""

    def _ollama_complete(self, prompt: str, system: str, max_tokens: int, json_mode: bool) -> str:
        cfg = get_config()
        try:
            import httpx
            payload = {
                "model": cfg.ollama_model,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {"num_predict": max_tokens, "temperature": 0.1},
            }
            if json_mode:
                payload["format"] = "json"
            resp = httpx.post(
                f"{cfg.ollama_url}/api/generate",
                json=payload,
                timeout=120,
            )
            data = resp.json()
            return data.get("response", "")
        except Exception as e:
            return json.dumps({"error": str(e)}) if json_mode else ""
