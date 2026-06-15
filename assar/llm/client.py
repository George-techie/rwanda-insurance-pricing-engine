"""Pluggable LLM client.

One code path (the OpenAI-compatible chat API) drives three backends, chosen by
the LLM_BACKEND env var:

    groq    -> https://api.groq.com/openai/v1   (default; fast, you have keys)
    ollama  -> http://localhost:11434/v1        (local Qwen, no API key)
    hf      -> https://router.huggingface.co/v1 (HF Inference Providers)

This honours the "Qwen + HF free models" intent (set LLM_BACKEND=ollama with a
Qwen model, or hf) while defaulting to Groq so an end-of-day demo doesn't hinge
on local GPU inference.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LLMConfig:
    backend: str
    base_url: str
    api_key: str
    model: str


def load_config() -> LLMConfig:
    backend = os.getenv("LLM_BACKEND", "groq").lower()
    if backend == "groq":
        return LLMConfig(
            backend,
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY", ""),
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        )
    if backend == "ollama":
        return LLMConfig(
            backend,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        )
    if backend == "hf":
        return LLMConfig(
            backend,
            base_url="https://router.huggingface.co/v1",
            api_key=os.getenv("HF_TOKEN", ""),
            model=os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct"),
        )
    raise ValueError(f"Unknown LLM_BACKEND '{backend}' (use groq | ollama | hf)")


class LLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or load_config()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key or "not-needed",
            )
        return self._client

    @property
    def ready(self) -> bool:
        # Ollama needs no key; the hosted backends do.
        if self.config.backend == "ollama":
            return True
        return bool(self.config.api_key)

    def chat(self, messages, tools=None, tool_choice="auto", temperature=0.1):
        """Return the raw assistant message object (has .content and .tool_calls)."""
        kwargs = dict(model=self.config.model, messages=messages, temperature=temperature)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message


def get_client() -> LLMClient:
    return LLMClient()
