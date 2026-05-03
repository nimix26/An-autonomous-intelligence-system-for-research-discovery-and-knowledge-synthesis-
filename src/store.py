import json
import hashlib
from pathlib import Path
from config import DATA_DIR, get_logger

log = get_logger("store")


class Store:
    def save_paper(self, paper_id: str, data: dict):
        self._write("papers", paper_id, data)

    def load_paper(self, paper_id: str):
        return self._read("papers", paper_id)

    def save_parsed(self, paper_id: str, data: dict):
        self._write("parsed", paper_id, data)

    def load_parsed(self, paper_id: str):
        return self._read("parsed", paper_id)

    def save_result(self, paper_id: str, data: dict):
        self._write("summaries", paper_id, data)

    def load_result(self, paper_id: str):
        return self._read("summaries", paper_id)

    def save_comparison(self, comp_id: str, data: dict):
        self._write("comparisons", comp_id, data)

    def cache_get(self, raw_key: str):
        key = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
        return self._read("cache", key)

    def cache_set(self, raw_key: str, data: dict):
        key = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
        self._write("cache", key, data)

    def _write(self, folder: str, name: str, data: dict):
        d = DATA_DIR / folder
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _read(self, folder: str, name: str):
        path = DATA_DIR / folder / f"{name}.json"
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)