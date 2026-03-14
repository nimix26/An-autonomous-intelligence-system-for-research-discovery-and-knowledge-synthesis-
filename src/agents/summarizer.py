"""
Agent 3 — Summarizer (Dual LLM: SambaNova Cloud + Local Ollama Fallback)

Priority order:
  1. SambaNova Cloud API (primary — fast, reliable)
  2. Local Ollama LLM (fallback when SambaNova is down)

Environment variables (set in .env file):
  SAMBANOVA_API_KEY=your-key-here                   ← Required
  SAMBANOVA_BASE_URL=https://api.sambanova.ai/v1    ← Default
  SAMBANOVA_MODEL=DeepSeek-V3.1-Terminus            ← Change model here
  LOCAL_LLM_API_KEY=your-ollama-key                 ← Optional (for remote Ollama)
  LOCAL_LLM_BASE_URL=http://localhost:11434          ← Ollama URL
  LOCAL_LLM_MODEL=llama3                             ← Ollama model
  LLM_STRATEGY=sambanova_first                       ← See strategies below

Strategies:
  sambanova_first  → Try SambaNova, fall back to Ollama (DEFAULT)
  local_first      → Try Ollama, fall back to SambaNova
  sambanova_only   → Only use SambaNova (no fallback)
  local_only       → Only use local Ollama (no fallback)
"""

import os
import re
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ─── SambaNova Configuration ────────────────────────────
SAMBANOVA_API_KEY = os.getenv("SAMBANOVA_API_KEY", "")
SAMBANOVA_BASE_URL = os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1")
SAMBANOVA_MODEL = os.getenv("SAMBANOVA_MODEL", "DeepSeek-V3.1-Terminus")

# ─── Local Ollama Configuration ─────────────────────────
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "")
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "llama3")

# ─── Strategy ───────────────────────────────────────────
LLM_STRATEGY = os.getenv("LLM_STRATEGY", "sambanova_first")


class Summarizer:
    """Agent 3: Generates research synthesis using SambaNova + Ollama fallback."""

    def __init__(self):
        # SambaNova config
        self.sn_key = SAMBANOVA_API_KEY
        self.sn_url = SAMBANOVA_BASE_URL.rstrip("/")
        self.sn_model = SAMBANOVA_MODEL

        # Local Ollama config
        self.local_key = LOCAL_LLM_API_KEY
        self.local_url = LOCAL_LLM_BASE_URL.rstrip("/") if LOCAL_LLM_BASE_URL else ""
        self.local_model = LOCAL_LLM_MODEL

        # Strategy
        self.strategy = LLM_STRATEGY.lower().strip()

        # ─── Startup Logging ─────────────────────────────
        logger.info(f"[Summarizer] ═══ LLM Configuration ═══")
        logger.info(f"[Summarizer] Strategy: {self.strategy}")
        logger.info(
            f"[Summarizer] SambaNova: model={self.sn_model}, "
            f"url={self.sn_url}, key={'SET' if self.sn_key else 'NOT SET'}"
        )
        logger.info(
            f"[Summarizer] Local Ollama: model={self.local_model}, "
            f"url={self.local_url}, key={'SET' if self.local_key else 'NOT SET'}"
        )

        # Safety check
        if not self.sn_key and not self.local_url:
            logger.error(
                "[Summarizer] CRITICAL: No LLM available! "
                "Set SAMBANOVA_API_KEY or LOCAL_LLM_BASE_URL in .env"
            )

    # ═══════════════════════════════════════════════════════
    #  PUBLIC METHOD
    # ═══════════════════════════════════════════════════════

    async def summarize(self, master_prompt: str, papers_text: str) -> dict:
        """Generate the final synthesis."""
        full_prompt = master_prompt + "\n" + papers_text

        logger.info(
            f"[Summarizer] Prompt size: {len(full_prompt)} chars | "
            f"Strategy: {self.strategy}"
        )

        try:
            raw_response = await self._call_with_strategy(full_prompt)
            logger.info(f"[Summarizer] Response: {len(raw_response)} chars")
            return self._parse_response(raw_response)

        except Exception as e:
            logger.error(f"[Summarizer] All LLM calls failed: {e}", exc_info=True)
            return {
                "summary": f"Error generating synthesis: {str(e)}",
                "key_insights": [],
                "gaps": [],
                "ideas": [],
            }

    # ═══════════════════════════════════════════════════════
    #  STRATEGY ROUTER
    # ═══════════════════════════════════════════════════════

    async def _call_with_strategy(self, prompt: str) -> str:
        """Route to LLM(s) based on configured strategy."""

        if self.strategy == "sambanova_only":
            return await self._call_sambanova(prompt)

        elif self.strategy == "local_only":
            return await self._call_local_ollama(prompt)

        elif self.strategy == "local_first":
            try:
                logger.info("[Summarizer] Trying Local Ollama first...")
                return await self._call_local_ollama(prompt)
            except Exception as e:
                logger.warning(f"[Summarizer] Local Ollama failed: {e}")
                if self.sn_key:
                    logger.info("[Summarizer] Falling back to SambaNova...")
                    return await self._call_sambanova(prompt)
                raise

        else:
            # Default: sambanova_first
            if self.sn_key:
                try:
                    logger.info("[Summarizer] Trying SambaNova API first...")
                    return await self._call_sambanova(prompt)
                except Exception as e:
                    logger.warning(f"[Summarizer] SambaNova failed: {e}")
                    if self.local_url:
                        logger.info("[Summarizer] Falling back to Local Ollama...")
                        return await self._call_local_ollama(prompt)
                    raise
            else:
                logger.info("[Summarizer] No SambaNova key — using Local Ollama...")
                return await self._call_local_ollama(prompt)

    # ═══════════════════════════════════════════════════════
    #  SAMBANOVA API (OpenAI-Compatible Chat Completions)
    # ═══════════════════════════════════════════════════════

    async def _call_sambanova(self, prompt: str) -> str:
        """
        Call SambaNova Cloud API.
        Uses OpenAI-compatible /chat/completions endpoint.
        
        To switch models, just change SAMBANOVA_MODEL in .env:
          - DeepSeek-V3.1-Terminus
          - Meta-Llama-3.3-70B-Instruct
          - Meta-Llama-3.1-405B-Instruct
          - Qwen2.5-72B-Instruct
          - Any model listed at https://cloud.sambanova.ai/
        
        To swap API keys, just change SAMBANOVA_API_KEY in .env.
        No code changes needed.
        """
        if not self.sn_key:
            raise RuntimeError("SAMBANOVA_API_KEY is not set in .env")

        url = f"{self.sn_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.sn_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.sn_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert research paper analyst and synthesizer. "
                        "You produce structured, well-organized academic summaries."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": 4096,
        }

        logger.info(
            f"[SambaNova] Calling {self.sn_model} at {self.sn_url} "
            f"({len(prompt)} chars)"
        )

        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(url, json=payload, headers=headers)

            # ── Handle errors ──
            if resp.status_code == 401:
                raise RuntimeError(
                    "SambaNova authentication failed — check SAMBANOVA_API_KEY in .env"
                )

            if resp.status_code == 403:
                raise RuntimeError(
                    "SambaNova access forbidden — your API key may not have "
                    "permission for this model"
                )

            if resp.status_code == 404:
                raise RuntimeError(
                    f"SambaNova model '{self.sn_model}' not found — "
                    f"check SAMBANOVA_MODEL in .env"
                )

            if resp.status_code == 429:
                raise RuntimeError(
                    "SambaNova rate limited — too many requests, try again shortly"
                )

            if resp.status_code != 200:
                error_text = resp.text[:500]
                logger.error(
                    f"[SambaNova] Error {resp.status_code}: {error_text}"
                )
                raise RuntimeError(
                    f"SambaNova API error {resp.status_code}: {error_text[:300]}"
                )

            # ── Parse response ──
            data = resp.json()

            try:
                text = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                logger.error(f"[SambaNova] Unexpected response format: {data}")
                raise RuntimeError(f"Failed to parse SambaNova response: {e}")

            if not text.strip():
                finish_reason = (
                    data.get("choices", [{}])[0].get("finish_reason", "unknown")
                )
                raise RuntimeError(
                    f"SambaNova returned empty text. Finish reason: {finish_reason}"
                )

            # ── Log usage stats if available ──
            usage = data.get("usage", {})
            if usage:
                logger.info(
                    f"[SambaNova] Tokens — "
                    f"prompt: {usage.get('prompt_tokens', '?')}, "
                    f"completion: {usage.get('completion_tokens', '?')}, "
                    f"total: {usage.get('total_tokens', '?')}"
                )

            logger.info(f"[SambaNova] Success — {len(text)} chars received ✓")
            return text

    # ═══════════════════════════════════════════════════════
    #  LOCAL OLLAMA LLM (Fallback)
    # ═══════════════════════════════════════════════════════

    async def _call_local_ollama(self, prompt: str) -> str:
        """Call Ollama instance (local or remote device)."""
        if not self.local_url:
            raise RuntimeError(
                "LOCAL_LLM_BASE_URL is not set — "
                "cannot use local Ollama as fallback"
            )

        headers = {"Content-Type": "application/json"}

        # Add auth if key is set (for remote Ollama behind reverse proxy)
        if self.local_key:
            headers["Authorization"] = f"Bearer {self.local_key}"

        # ── Health check (quick timeout) ──
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                health = await client.get(
                    f"{self.local_url}/api/tags",
                    headers=headers,
                )
                if health.status_code != 200:
                    raise RuntimeError(
                        f"Ollama returned status {health.status_code}"
                    )
                logger.info("[Local Ollama] Device reachable ✓")
            except httpx.ConnectError:
                raise RuntimeError("Ollama unreachable (connection refused)")
            except httpx.TimeoutException:
                raise RuntimeError("Ollama unreachable (timeout)")

        # ── Generate ──
        payload = {
            "model": self.local_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 4096,
                "top_p": 0.9,
            },
        }

        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{self.local_url}/api/generate",
                json=payload,
                headers=headers,
            )

            if resp.status_code == 401:
                raise RuntimeError("Ollama auth failed — check LOCAL_LLM_API_KEY")
            if resp.status_code == 404:
                raise RuntimeError(
                    f"Model '{self.local_model}' not found on Ollama"
                )

            resp.raise_for_status()
            data = resp.json()
            text = data.get("response", "")

            if not text.strip():
                raise RuntimeError("Ollama returned empty response")

            logger.info(f"[Local Ollama] Success — {len(text)} chars ✓")
            return text

    # ════════════════════════════════════════════════���══════
    #  RESPONSE PARSING
    # ═══════════════════════════════════════════════════════

    def _parse_response(self, raw: str) -> dict:
        """Parse the LLM response into structured output."""
        result = {
            "summary": "",
            "key_insights": [],
            "gaps": [],
            "ideas": [],
        }

        # Extract JSON blocks
        insights = self._extract_json_block(raw, "json_insights")
        gaps = self._extract_json_block(raw, "json_gaps")
        ideas = self._extract_json_block(raw, "json_ideas")

        if insights:
            result["key_insights"] = insights
        if gaps:
            result["gaps"] = gaps
        if ideas:
            result["ideas"] = ideas

        # Summary is everything before the first JSON block
        summary = raw
        for marker in ["```json_insights", "```json_gaps", "```json_ideas"]:
            idx = summary.find(marker)
            if idx != -1:
                summary = summary[:idx]

        result["summary"] = summary.strip()

        # Fallback extraction from plain text
        if not result["key_insights"]:
            result["key_insights"] = self._extract_list_from_text(raw, "key insight")
        if not result["gaps"]:
            result["gaps"] = self._extract_list_from_text(raw, "gap")
        if not result["ideas"]:
            result["ideas"] = self._extract_list_from_text(raw, "idea")

        return result

    def _extract_json_block(self, text: str, block_name: str) -> Optional[list]:
        """Extract a JSON array from a named code block."""
        pattern = rf"```{block_name}\s*\n(.*?)\n\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.warning(
                    f"[Summarizer] Failed to parse {block_name} JSON block"
                )
        return None

    def _extract_list_from_text(self, text: str, keyword: str) -> list:
        """Fallback: extract list items near a keyword."""
        items = []
        lines = text.split("\n")
        capture = False
        for line in lines:
            if keyword.lower() in line.lower() and (":" in line or "#" in line):
                capture = True
                continue
            if capture:
                stripped = line.strip()
                if stripped.startswith(("-", "*", "•")):
                    items.append(stripped.lstrip("-*• ").strip())
                elif stripped == "" and items:
                    break
                elif stripped and not stripped.startswith(("-", "*", "•", "#")):
                    break
        return items[:10]