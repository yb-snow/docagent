"""Vendor name semantic matching using ChromaDB + rapidfuzz."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import chromadb
from chromadb.utils import embedding_functions
from rapidfuzz import fuzz, process as rfprocess

from config import CHROMA_PERSIST_DIR, FUZZY_VENDOR_THRESHOLD, VENDOR_COLLECTION

_VENDORS_FILE = Path(__file__).parent.parent / "data" / "vendors.txt"


class VendorMatcher:
    def __init__(self):
        self._client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        self._ef     = embedding_functions.DefaultEmbeddingFunction()
        self._col    = self._client.get_or_create_collection(
            name=VENDOR_COLLECTION,
            embedding_function=self._ef,
        )
        self._seed_if_empty()

    def _seed_if_empty(self) -> None:
        if self._col.count() == 0 and _VENDORS_FILE.exists():
            vendors = [v.strip() for v in _VENDORS_FILE.read_text().splitlines() if v.strip()]
            self._add(vendors)

    def _add(self, vendors: list[str]) -> None:
        existing = set(self._col.get()["documents"] or [])
        new = [v for v in vendors if v not in existing]
        if new:
            offset = len(existing)
            self._col.add(
                documents=new,
                ids=[f"vendor_{offset + i}" for i in range(len(new))],
            )

    def add_vendors(self, vendors: list[str]) -> int:
        before = self._col.count()
        self._add(vendors)
        return self._col.count() - before

    def load_from_file(self, filepath: str) -> None:
        vendors = [v.strip() for v in Path(filepath).read_text().splitlines() if v.strip()]
        added = self.add_vendors(vendors)
        print(f"Loaded {added} new vendor(s) from {filepath}. Total: {self._col.count()}")

    def match(self, vendor_name: str, top_k: int = 3) -> Optional[str]:
        if self._col.count() == 0:
            return vendor_name
        results = self._col.query(
            query_texts=[vendor_name],
            n_results=min(top_k, self._col.count()),
        )
        candidates = results["documents"][0] if results["documents"] else []
        if not candidates:
            return None
        best, score, _ = rfprocess.extractOne(vendor_name, candidates, scorer=fuzz.token_sort_ratio)
        return best if score >= FUZZY_VENDOR_THRESHOLD else None

    def is_known_vendor(self, vendor_name: str) -> Tuple[bool, Optional[str]]:
        matched = self.match(vendor_name)
        return (matched is not None), matched
