"""Lazy, bounded local Indra worker. Books and OCR text never leave this machine."""
from __future__ import annotations

import atexit
import base64
import copy
import hashlib
import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from contextlib import nullcontext
from pathlib import Path

from .cancellation import OperationCancelled

MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_CACHE_BYTES = 4 * 1024 * 1024
MAX_CACHE_ENTRIES = 16
MAX_IMAGE_PIXELS = 24_000_000
IDLE_SECONDS = 60


def resource_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def model_manifest():
    return json.loads((resource_root() / "data/indra_ocr_models.json").read_text(encoding="utf-8"))


def model_directory():
    # Deliberately ignore INDRA_OCR_MODEL_DIR and automatic Hugging Face lookup:
    # this application uses exactly the locally bundled, pinned models.
    return resource_root() / "ocr_models/indra"


def validate_models():
    manifest = model_manifest()
    directory = model_directory()
    for item in manifest["files"]:
        path = directory / item["name"]
        if not path.is_file() or path.stat().st_size != item["bytes"]:
            raise RuntimeError(f"Missing or corrupt Indra model: {item['name']}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != item["sha256"]:
            raise RuntimeError(f"Indra model integrity check failed: {item['name']}")
    return manifest


def available():
    try:
        return (importlib.util.find_spec("indra_ocr") is not None
                and all((model_directory() / item["name"]).is_file() for item in model_manifest()["files"]))
    except (OSError, ValueError, KeyError):
        return False


def worker_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ocr-worker"]
    return [sys.executable, "-B", str(resource_root() / "main.py"), "--ocr-worker"]


class LocalOcrWorker:
    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._cache = OrderedDict()
        self._cache_bytes = 0
        self._idle_timer = None
        self._generation = 0

    def _stop(self):
        process, self._process = self._process, None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()

    def close(self):
        with self._lock:
            self._generation += 1
            if self._idle_timer:
                self._idle_timer.cancel()
            self._stop()
            self._cache.clear()
            self._cache_bytes = 0

    def _idle_close(self, generation):
        with self._lock:
            if generation == self._generation:
                self._stop()

    def _start(self):
        if self._process is None or self._process.poll() is not None:
            self._stop()
            env = os.environ.copy()
            env.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1")
            self._process = subprocess.Popen(
                worker_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

    def recognize(self, image_bytes, *, timeout=45, cancellation=None):
        if cancellation:
            cancellation.raise_if_cancelled()
        if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
            return {"error": "Empty or oversized OCR image", "text": "", "lines": []}
        deadline = time.monotonic() + max(0.1, float(timeout))
        while not self._lock.acquire(timeout=0.05):
            if cancellation:
                cancellation.raise_if_cancelled()
            if time.monotonic() >= deadline:
                return {"error": "Indra OCR queue timed out", "text": "", "lines": []}
        try:
            if cancellation:
                cancellation.raise_if_cancelled()
            self._generation += 1
            if self._idle_timer:
                self._idle_timer.cancel()
            key = hashlib.sha256(image_bytes).digest()
            if key in self._cache:
                cached, size = self._cache.pop(key)
                self._cache[key] = (cached, size)
                result = copy.deepcopy(cached)
                result["inference_cache"] = True
                return result
            self._start()
            process = self._process
            replies = queue.Queue(maxsize=1)

            def read_reply():
                try:
                    replies.put(process.stdout.readline(MAX_RESPONSE_BYTES + 1))
                except (OSError, ValueError):
                    replies.put(b"")

            reader = threading.Thread(target=read_reply, daemon=True, name="IndraOcrReply")
            reader.start()
            with cancellation.track_process(process) if cancellation else nullcontext():
                request = json.dumps({"image": base64.b64encode(image_bytes).decode("ascii")}).encode("ascii")
                process.stdin.write(request + b"\n")
                process.stdin.flush()
                while True:
                    if cancellation:
                        cancellation.raise_if_cancelled()
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Indra OCR timed out")
                    try:
                        raw = replies.get(timeout=min(0.05, max(0.001, deadline - time.monotonic())))
                        break
                    except queue.Empty:
                        continue
            if not raw or len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Indra OCR worker returned an invalid response")
            result = json.loads(raw)
            if not isinstance(result, dict) or not isinstance(result.get("lines"), list):
                raise RuntimeError("Indra OCR worker returned invalid page data")
            if result.get("error"):
                self._stop()
            else:
                size = len(raw)
                self._cache[key] = (copy.deepcopy(result), size)
                self._cache_bytes += size
                while len(self._cache) > MAX_CACHE_ENTRIES or self._cache_bytes > MAX_CACHE_BYTES:
                    _, (_, removed_size) = self._cache.popitem(last=False)
                    self._cache_bytes -= removed_size
            return result
        except OperationCancelled:
            self._stop()
            raise
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            self._stop()
            if cancellation:
                cancellation.raise_if_cancelled()
            return {"error": str(exc), "text": "", "lines": []}
        finally:
            self._idle_timer = threading.Timer(IDLE_SECONDS, self._idle_close, (self._generation,))
            self._idle_timer.daemon = True
            self._idle_timer.start()
            self._lock.release()


_WORKER = LocalOcrWorker()
atexit.register(_WORKER.close)


def recognize(image_bytes, *, timeout=45, cancellation=None):
    return _WORKER.recognize(image_bytes, timeout=timeout, cancellation=cancellation)


def close():
    _WORKER.close()


def _retry_weak_lines(engine, pixels, page):
    """Recover clipped short titles with one bounded recognition-only batch.

    The detector can omit an isolated glyph (e.g. the three strokes of 三).
    Expanding only weak, short line boxes keeps the same detected reading order;
    it does not repeat page detection, orientation or layout inference.
    """
    if page.vertical or abs(page.skew) > 5:
        return 0
    import numpy as np

    upright = np.rot90(pixels, page.rotation // 90) if page.rotation else pixels
    targets, boxes = [], []
    for line in page.lines:
        if line.text.strip() and float(line.conf) >= 0.55:
            continue
        x0, y0, x1, y1 = map(float, line.box[:4])
        height = y1 - y0
        if height < 8 or x1 - x0 > 12 * height:
            continue
        targets.append(line)
        boxes.append([max(0, x0 - 1.5 * height), max(0, y0 - 0.1 * height),
                      min(upright.shape[1], x1 + 1.5 * height), min(upright.shape[0], y1 + 0.1 * height)])
        if len(targets) == 8:
            break
    if not targets:
        return 0
    started = time.monotonic()
    readings = engine.recognize(upright, np.asarray(boxes, dtype=np.float32))
    recovered = 0
    for line, box, (text, confidence, _) in zip(targets, boxes, readings):
        if text.strip() and confidence >= max(0.75, float(line.conf) + 0.1):
            line.text, line.conf, line.box = text, confidence, box
            recovered += 1
    page.timings["weak_line_retry_ms"] = round((time.monotonic() - started) * 1000, 3)
    return recovered


def worker_main():
    """Private pipe protocol; no servers, downloads, GUI imports or user profile."""
    import contextlib
    import io

    def pipe_stream(stream, identifier, mode):
        if stream is not None:
            return stream.buffer
        # PyInstaller's windowed bootloader leaves sys.stdin/stdout as None.
        # Use only the explicit pipes inherited from our Popen worker launcher.
        if os.name != "nt":
            raise RuntimeError("OCR worker requires private input/output pipes")
        import ctypes
        import msvcrt
        from ctypes import wintypes

        get_handle = ctypes.windll.kernel32.GetStdHandle
        get_handle.argtypes = [wintypes.DWORD]
        get_handle.restype = wintypes.HANDLE
        handle = get_handle(identifier & 0xFFFFFFFF)
        if handle in (None, 0, ctypes.c_void_p(-1).value):
            raise RuntimeError("OCR worker requires private input/output pipes")
        flags = os.O_BINARY | (os.O_RDONLY if mode == "rb" else os.O_WRONLY)
        return os.fdopen(msvcrt.open_osfhandle(handle, flags), mode)

    input_stream = pipe_stream(sys.stdin, -10, "rb")
    output_stream = pipe_stream(sys.stdout, -11, "wb")

    def no_network(event, arguments):
        if event in {"socket.connect", "socket.getaddrinfo"}:
            raise RuntimeError("Network access is disabled in the local OCR worker")

    sys.addaudithook(no_network)
    engine = None
    while raw := input_stream.readline(MAX_IMAGE_BYTES * 4 // 3 + 256):
        if not raw.endswith(b"\n"):
            return 2
        try:
            request = json.loads(raw)
            image_bytes = base64.b64decode(request["image"], validate=True)
            if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
                raise ValueError("Empty or oversized OCR image")
            with contextlib.redirect_stdout(sys.stderr):
                if engine is None:
                    validate_models()
                    import onnxruntime
                    onnxruntime.disable_telemetry_events()
                    from indra_ocr import OrtOCR
                    threads = min(4, max(1, (os.cpu_count() or 2) // 2))
                    engine = OrtOCR(model_directory(), threads=threads, providers=["CPUExecutionProvider"], furniture=True)
                import numpy as np
                from PIL import Image, ImageOps

                with Image.open(io.BytesIO(image_bytes)) as source:
                    if source.width * source.height > MAX_IMAGE_PIXELS:
                        raise ValueError("OCR image exceeds the 24 megapixel limit")
                    upright = ImageOps.exif_transpose(source)
                    try:
                        upright.thumbnail((2800, 2800))
                        with upright.convert("L") as gray:
                            pixels = np.array(gray)
                    finally:
                        if upright is not source:
                            upright.close()
                page = engine(pixels)
                recovered = _retry_weak_lines(engine, pixels, page)
            height, width = pixels.shape
            if page.rotation % 180:
                width, height = height, width
            lines = []
            for line in page.lines[:4096]:
                if not line.text.strip():
                    continue
                x0, y0, x1, y1 = (float(x) for x in line.box[:4])
                lines.append({"text": line.text[:2000], "page": 1, "block": 1,
                              "line": len(lines) + 1, "x": round(x0), "y": round(y0),
                              "width": max(1, round(x1 - x0)), "height": max(1, round(y1 - y0)),
                              "confidence": round(min(100, max(0, float(line.conf) * 100)), 1)})
            result = {"text": "\n".join(x["text"] for x in lines), "lines": lines,
                      "width": width, "height": height, "rotation": page.rotation,
                      "timings": page.timings, "recovered_lines": recovered,
                      "unreadable_lines": sum(not line.text.strip() for line in page.lines),
                      "worker_threads": threads, "error": None}
        except Exception as exc:
            result = {"text": "", "lines": [], "error": f"Indra OCR: {type(exc).__name__}: {exc}"}
        encoded = json.dumps(result, ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_RESPONSE_BYTES - 1:
            encoded = b'{"text":"","lines":[],"error":"Indra OCR output exceeds the size limit"}'
        output_stream.write(encoded + b"\n")
        output_stream.flush()
    return 0
