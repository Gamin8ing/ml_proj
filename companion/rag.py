"""
Minimal RAG stub for CAIGA companion.

Provides a small class with a retrieve() method. By default returns an empty
list unless sentence-transformers is available and a KB is provided elsewhere.
This keeps the companion runnable without extra deps.
"""

from __future__ import annotations

from typing import List


class RAG:
	def __init__(self, *args, **kwargs) -> None:
		pass

	def retrieve(self, query: str, top_k: int = 3) -> List[str]:
		return []
