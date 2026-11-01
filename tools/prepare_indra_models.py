"""Fetch the pinned, hash-checked OCR models at build time, never during OCR."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(*, check_only=False):
    manifest = json.loads((ROOT / "data/indra_ocr_models.json").read_text(encoding="utf-8"))
    directory = ROOT / "ocr_models/indra"

    def ensure(item):
        name = item["name"]
        if Path(name).name != name or "\\" in name:
            raise ValueError("Invalid model filename")
        path = directory / name
        if path.is_file() and path.stat().st_size == item["bytes"] and file_hash(path) == item["sha256"]:
            return
        if check_only:
            raise RuntimeError(f"Missing or corrupt Indra model: {name}; run tools/prepare_indra_models.py")
        directory.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{manifest['modelRepository']}/resolve/{manifest['modelRevision']}/{name}"
        descriptor, temporary = tempfile.mkstemp(prefix=name + ".", suffix=".part", dir=directory)
        try:
            digest = hashlib.sha256()
            total = 0
            with os.fdopen(descriptor, "wb") as target, urllib.request.urlopen(url, timeout=30) as response:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > item["bytes"]:
                        raise RuntimeError(f"Unexpected model size: {name}")
                    target.write(chunk)
                    digest.update(chunk)
            if total != item["bytes"] or digest.hexdigest() != item["sha256"]:
                raise RuntimeError(f"Model integrity check failed: {name}")
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(ensure, manifest["files"]))
    print(f"Indra OCR: {len(manifest['files'])} pinned model/license files verified ({manifest['modelRevision']}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check without network access or writes")
    arguments = parser.parse_args()
    try:
        prepare(check_only=arguments.check)
    except Exception as exc:
        print(f"Indra models: {exc}", file=sys.stderr)
        raise SystemExit(1)
