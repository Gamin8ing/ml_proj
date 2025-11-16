"""
llm_wrapper.py - Pluggable LLM interface with Gemini backup

This module exposes helper functions to generate short, factual, spoiler-bounded
tips using an LLM. By default, it requires no external keys and falls back to a
simple concatenation stub. If explicitly enabled with environment variables and
an API key, it will use Google Gemini via the `google-generativeai` package.

Environment variables:
  - GEMINI_ENABLED=false | true
  - GEMINI_API_KEY=<your_key>
  - GEMINI_MODEL=gemini-1.5-flash  (good default for speed/cost)
  - GEMINI_TEMPERATURE=0.7
  - GEMINI_MAX_TOKENS=120

Safe defaults: If GEMINI_ENABLED is not true or an API key is missing, the
functions return a stubbed, non-LLM paraphrase so the app remains fully local
and runnable without secrets.
"""

from __future__ import annotations

import os
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _gemini_config():
	"""Read Gemini config from environment and validate minimal requirements."""
	enabled = os.getenv("GEMINI_ENABLED", "false").lower() == "true"
	api_key = os.getenv("GEMINI_API_KEY", "").strip()
	model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
	temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
	max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "120"))

	if not enabled:
		return {
			"enabled": False,
			"reason": "GEMINI_ENABLED is not true"
		}
	if not api_key:
		return {
			"enabled": False,
			"reason": "GEMINI_API_KEY not set"
		}
	return {
		"enabled": True,
		"api_key": api_key,
		"model": model,
		"temperature": temperature,
		"max_tokens": max_tokens,
	}


def _try_import_gemini():
	"""Import the Gemini SDK lazily to avoid hard dependency at startup."""
	try:
		import google.generativeai as genai  # type: ignore
		return genai
	except Exception as e:
		logger.debug(f"Gemini SDK import failed: {e}")
		return None


def paraphrase_with_context(
	query: str,
	docs: List[str],
	max_length: int = 150,
	system_prompt: Optional[str] = None,
) -> str:
	"""
	Produce a concise, factual tip given a short query and retrieved docs.

	Behavior:
	  - If GEMINI is enabled and configured, call Gemini to paraphrase concisely
		using the docs as grounding context.
	  - Otherwise, fall back to a deterministic, non-LLM stub: concatenate top
		doc snippets and trim.

	Args:
	  query: The base tip or instruction to be phrased for chat.
	  docs: Top-k retrieved snippets used for factual grounding.
	  max_length: Soft cap on characters for the final message (trimmed if over).
	  system_prompt: Optional extra instructions for style and safety.

	Returns:
	  A short string suitable for in-game chat. Never raises on missing deps.
	"""
	cfg = _gemini_config()

	# Non-LLM fallback (default path, no secrets required)
	if not cfg.get("enabled"):
		if not docs:
			return _trim(f"{query}", max_length)
		joined = " ".join(docs[:3])
		return _trim(f"{query} (Context: {joined})", max_length)

	genai = _try_import_gemini()
	if genai is None:
		logger.warning("Gemini enabled but SDK not installed; falling back to stub.")
		if not docs:
			return _trim(f"{query}", max_length)
		joined = " ".join(docs[:3])
		return _trim(f"{query} (Context: {joined})", max_length)

	# Call Gemini
	try:
		genai.configure(api_key=cfg["api_key"])

		model_name = cfg["model"]
		temperature = cfg["temperature"]
		max_tokens = cfg["max_tokens"]

		# Compose prompt: concise, factual, spoiler-bounded
		base_system = (
			"You are a helpful Minecraft in-game assistant. "
			"Write one short, factual tip grounded ONLY in the provided context. "
			"Avoid spoilers beyond the context. Keep it under 1-2 sentences."
		)
		if system_prompt:
			base_system = base_system + "\n" + system_prompt

		context_block = "\n\n".join(docs[:3]) if docs else ""
		user_msg = (
			f"Context:\n{context_block}\n\n"
			f"Tip request: {query}\n\n"
			"Return only the tip text, no preamble."
		)

		# New SDK unified interface
		model = genai.GenerativeModel(model_name)
		resp = model.generate_content(
			[
				{"role": "system", "parts": [base_system]},
				{"role": "user", "parts": [user_msg]},
			],
			generation_config={
				"temperature": temperature,
				"max_output_tokens": max_tokens,
			},
		)

		text = _extract_text(resp)
		if not text:
			raise RuntimeError("Empty response from Gemini")
		return _trim(text, max_length)

	except Exception as e:
		logger.warning(f"Gemini call failed: {e}; falling back to stub.")
		if not docs:
			return _trim(f"{query}", max_length)
		joined = " ".join(docs[:3])
		return _trim(f"{query} (Context: {joined})", max_length)


def paraphrase_tip_with_recipe(
	tip_text: str,
	recipe_query: str,
	rag_instance,
	max_length: int = 150,
) -> str:
	"""
	If a tip contains a {recipe} placeholder, retrieve context via RAG and
	paraphrase with Gemini (if available) or fallback stub.
	"""
	if not rag_instance:
		return tip_text.replace("{recipe}", "[recipe not available]")

	docs = []
	try:
		if hasattr(rag_instance, "retrieve"):
			docs = rag_instance.retrieve(recipe_query, top_k=3) or []
	except Exception as e:
		logger.debug(f"RAG retrieval failed: {e}")

	recipe_info = paraphrase_with_context(recipe_query, docs, max_length=max_length)
	return tip_text.replace("{recipe}", recipe_info)


# ------------------ helpers ------------------

def _extract_text(resp) -> str:
	"""Best-effort extraction of text from Gemini SDK response."""
	try:
		# google-generativeai responses often have .text or candidates[].content.parts[].text
		if hasattr(resp, "text") and resp.text:
			return resp.text.strip()
		# Fallbacks
		candidates = getattr(resp, "candidates", None) or []
		for c in candidates:
			content = getattr(c, "content", None)
			if not content:
				continue
			parts = getattr(content, "parts", None) or []
			for p in parts:
				t = getattr(p, "text", None)
				if t:
					return str(t).strip()
	except Exception:
		pass
	return ""


def _trim(text: str, max_length: int) -> str:
	text = (text or "").strip()
	if max_length > 0 and len(text) > max_length:
		return text[:max_length - 3].rstrip() + "..."
	return text
