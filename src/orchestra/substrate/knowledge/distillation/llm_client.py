"""
LLM Client Abstraction

Unified interface for LLM providers (Anthropic, OpenAI).
Handles retries, rate limiting, and response parsing.

Part of USD Cognitive Substrate - Knowledge Prims Distillation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .config import DistillationConfig, LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM call.

    Attributes:
        content: The text content of the response
        model: Model that generated the response
        input_tokens: Tokens in the prompt
        output_tokens: Tokens in the response
        latency_ms: Time taken for the request
        cached: Whether response came from cache
        raw_response: Original response object (provider-specific)
    """
    content: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False
    raw_response: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (without raw_response)."""
        return {
            "content": self.content,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
        }


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    def __init__(self, config: DistillationConfig) -> None:
        self.config = config
        self._cache: dict[str, LLMResponse] = {}
        self._cache_dir = config.output_dir / ".cache"

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate a response from the LLM.

        Args:
            prompt: User message/prompt
            system: Optional system message
            temperature: Override config temperature
            max_tokens: Override config max_tokens

        Returns:
            LLMResponse with content and metadata
        """
        pass

    def _cache_key(self, prompt: str, system: str | None, temperature: float) -> str:
        """Generate deterministic cache key.

        Uses full SHA-256 (64 chars) to prevent hash collisions.
        ThinkingMachines [He2025] batch-invariance compliant.
        """
        data = f"{self.config.model_name}:{system or ''}:{prompt}:{temperature}"
        return hashlib.sha256(data.encode()).hexdigest()  # Full 64-char hash

    def _load_cache(self) -> None:
        """Load cache from disk."""
        cache_file = self._cache_dir / "llm_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    raw = json.load(f)
                    for key, val in raw.items():
                        self._cache[key] = LLMResponse(
                            content=val["content"],
                            model=val.get("model", ""),
                            input_tokens=val.get("input_tokens", 0),
                            output_tokens=val.get("output_tokens", 0),
                            latency_ms=val.get("latency_ms", 0.0),
                            cached=True,
                        )
                logger.info(f"Loaded {len(self._cache)} cached responses")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self) -> None:
        """Persist cache to disk."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._cache_dir / "llm_cache.json"
        try:
            data = {k: v.to_dict() for k, v in self._cache.items()}
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    async def _retry_with_backoff(
        self,
        coro_factory,
        max_retries: int | None = None,
    ) -> Any:
        """Execute with exponential backoff on failure.

        Args:
            coro_factory: Callable that returns an awaitable
            max_retries: Override config retry_count

        Returns:
            Result of the coroutine

        Raises:
            Exception: If all retries exhausted
        """
        retries = max_retries or self.config.retry_count
        delay = self.config.retry_delay_seconds

        for attempt in range(retries + 1):
            try:
                return await coro_factory()
            except Exception as e:
                if attempt == retries:
                    logger.error(f"All {retries} retries exhausted: {e}")
                    raise
                wait_time = delay * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.1f}s")
                await asyncio.sleep(wait_time)


class AnthropicClient(BaseLLMClient):
    """Anthropic Claude API client."""

    def __init__(self, config: DistillationConfig) -> None:
        super().__init__(config)
        self._client = None
        if config.enable_caching:
            self._load_cache()

    def _get_client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package required. Install with: pip install anthropic"
                )

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable not set"
                )
            self._client = Anthropic(api_key=api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate response from Claude."""
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens or self.config.max_tokens

        # Check cache
        if self.config.enable_caching:
            cache_key = self._cache_key(prompt, system, temp)
            if cache_key in self._cache:
                logger.debug(f"Cache hit for key {cache_key[:8]}")
                return self._cache[cache_key]

        async def _make_request():
            client = self._get_client()
            start = time.perf_counter()

            # Build messages
            messages = [{"role": "user", "content": prompt}]
            kwargs = {
                "model": self.config.model_name,
                "max_tokens": tokens,
                "temperature": temp,
                "messages": messages,
            }
            if system:
                kwargs["system"] = system

            # Run sync client in thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.messages.create(**kwargs)
            )

            elapsed_ms = (time.perf_counter() - start) * 1000

            content = response.content[0].text if response.content else ""

            return LLMResponse(
                content=content,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=elapsed_ms,
                cached=False,
                raw_response=response,
            )

        result = await self._retry_with_backoff(_make_request)

        # Cache result
        if self.config.enable_caching:
            cache_key = self._cache_key(prompt, system, temp)
            self._cache[cache_key] = result
            self._save_cache()

        return result


class OpenAIClient(BaseLLMClient):
    """OpenAI API client."""

    def __init__(self, config: DistillationConfig) -> None:
        super().__init__(config)
        self._client = None
        if config.enable_caching:
            self._load_cache()

    def _get_client(self):
        """Lazy-load OpenAI client."""
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError:
                raise ImportError(
                    "openai package required. Install with: pip install openai"
                )

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY environment variable not set"
                )
            self._client = OpenAI(api_key=api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate response from OpenAI model."""
        temp = temperature if temperature is not None else self.config.temperature
        tokens = max_tokens or self.config.max_tokens

        # Check cache
        if self.config.enable_caching:
            cache_key = self._cache_key(prompt, system, temp)
            if cache_key in self._cache:
                logger.debug(f"Cache hit for key {cache_key[:8]}")
                return self._cache[cache_key]

        async def _make_request():
            client = self._get_client()
            start = time.perf_counter()

            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=self.config.model_name,
                    messages=messages,
                    max_tokens=tokens,
                    temperature=temp,
                )
            )

            elapsed_ms = (time.perf_counter() - start) * 1000

            content = response.choices[0].message.content if response.choices else ""

            return LLMResponse(
                content=content or "",
                model=response.model,
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0,
                latency_ms=elapsed_ms,
                cached=False,
                raw_response=response,
            )

        result = await self._retry_with_backoff(_make_request)

        # Cache result
        if self.config.enable_caching:
            cache_key = self._cache_key(prompt, system, temp)
            self._cache[cache_key] = result
            self._save_cache()

        return result


def create_llm_client(config: DistillationConfig) -> BaseLLMClient:
    """Factory function to create appropriate LLM client.

    Args:
        config: Distillation configuration

    Returns:
        Configured LLM client instance

    Raises:
        ValueError: If provider not supported
    """
    if config.llm_provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(config)
    elif config.llm_provider == LLMProvider.OPENAI:
        return OpenAIClient(config)
    else:
        raise ValueError(f"Unsupported LLM provider: {config.llm_provider}")
