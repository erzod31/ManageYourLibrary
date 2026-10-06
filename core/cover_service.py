"""Bounded local cover extraction and thumbnail caching for the library UI."""

from __future__ import annotations

import hashlib
import io
import os
import posixpath
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from PIL import Image, ImageOps, UnidentifiedImageError

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
MAX_ARCHIVE_IMAGE_BYTES = 20 * 1024 * 1024
MAX_REMOTE_IMAGE_BYTES = 8 * 1024 * 1024
DEFAULT_CACHE_BYTES = 100 * 1024 * 1024
REMOTE_TIMEOUT_SECONDS = 6
MISS_CACHE_SECONDS = 6 * 60 * 60
REMOTE_MISS_CACHE_SECONDS = 30
ALLOWED_COVER_HOSTS = {"covers.openlibrary.org"}


class CoverService:
    _prune_lock = threading.Lock()
    _remote_lock = threading.Lock()
    _last_remote_request = 0.0
    _remote_interval_seconds = 0.35

    def __init__(
        self,
        cache_dir: Path,
        size=(120, 172),
        *,
        max_cache_bytes=DEFAULT_CACHE_BYTES,
        urlopen_func=None,
    ):
        self.cache_dir = Path(cache_dir)
        self.size = tuple(size)
        self.max_cache_bytes = max(1, int(max_cache_bytes))
        self.urlopen_func = urlopen_func or urllib.request.urlopen
        self._last_prune = 0.0

    def thumbnail_path(self, source: Path, remote_url: str = "") -> Path | None:
        source = Path(source)
        try:
            stat = source.stat()
        except OSError:
            return None
        remote_url = self._validated_remote_url(remote_url)
        key = hashlib.sha256(
            f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{self.size}|{remote_url}".encode(
                "utf-8", "surrogatepass"
            )
        ).hexdigest()
        destination = self.cache_dir / f"{key}.webp"
        miss_marker = self.cache_dir / f"{key}.miss"
        if destination.exists():
            self._touch_if_stale(destination)
            self._prune_if_due()
            return destination
        if miss_marker.exists():
            try:
                # Network outages are transient. This also expires old markers
                # created offline by earlier releases instead of waiting 6h.
                ttl = REMOTE_MISS_CACHE_SECONDS if remote_url else MISS_CACHE_SECONDS
                if time.time() - miss_marker.stat().st_mtime < ttl:
                    return None
                miss_marker.unlink()
            except OSError:
                pass
        image = self._extract(source)
        if image is None and remote_url:
            image = self._fetch_remote(remote_url)
        if image is None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            # Offline is a deferred request, not proof that a cover is absent.
            if remote_url and os.environ.get("MANAGE_YOUR_LIBRARY_OFFLINE", "").strip().casefold() in {"1", "true", "yes", "on"}:
                return None
            try:
                miss_marker.touch()
            except OSError:
                pass
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        canvas = Image.new("RGB", self.size, "#e9eef5")
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        normalized.thumbnail(self.size, Image.Resampling.LANCZOS)
        x = (self.size[0] - normalized.width) // 2
        y = (self.size[1] - normalized.height) // 2
        canvas.paste(normalized, (x, y))
        temporary = destination.with_name(f".{destination.name}.{threading.get_ident()}.tmp")
        canvas.save(temporary, format="WEBP", quality=82, method=4)
        temporary.replace(destination)
        try:
            miss_marker.unlink(missing_ok=True)
        except OSError:
            pass
        self._prune_if_due()
        return destination

    @staticmethod
    def _validated_remote_url(value: str) -> str:
        value = str(value or "").strip()
        if not value:
            return ""
        try:
            parsed = urllib.parse.urlsplit(value)
        except ValueError:
            return ""
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or host not in ALLOWED_COVER_HOSTS or parsed.username or parsed.password:
            return ""
        return urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))

    def _fetch_remote(self, url: str) -> Image.Image | None:
        if os.environ.get("MANAGE_YOUR_LIBRARY_OFFLINE", "").strip().casefold() in {"1", "true", "yes", "on"}:
            return None
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ManageYourLibrary/0.5 (cover preview; +https://github.com/erzod31/ManageYourLibrary)",
                "Accept": "image/avif,image/webp,image/*;q=0.8",
            },
        )
        try:
            with self._remote_lock:
                elapsed = time.monotonic() - type(self)._last_remote_request
                if elapsed < self._remote_interval_seconds:
                    time.sleep(self._remote_interval_seconds - elapsed)
                type(self)._last_remote_request = time.monotonic()
            with self.urlopen_func(request, timeout=REMOTE_TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    return None
                final_url = self._validated_remote_url(getattr(response, "geturl", lambda: url)())
                if not final_url:
                    return None
                content_type = str(response.headers.get("Content-Type", "")).casefold()
                if content_type and not content_type.startswith("image/"):
                    return None
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > MAX_REMOTE_IMAGE_BYTES:
                    return None
                data = response.read(MAX_REMOTE_IMAGE_BYTES + 1)
            if not data or len(data) > MAX_REMOTE_IMAGE_BYTES:
                return None
            with Image.open(io.BytesIO(data)) as image:
                return image.copy()
        except (OSError, TypeError, ValueError, UnidentifiedImageError):
            return None

    @staticmethod
    def _touch_if_stale(path: Path):
        try:
            if time.time() - path.stat().st_mtime > 24 * 60 * 60:
                path.touch()
        except OSError:
            pass

    def _prune_if_due(self):
        now = time.monotonic()
        if now - self._last_prune < 60:
            return
        self._last_prune = now
        self.prune_cache()

    def prune_cache(self):
        if not self.cache_dir.exists():
            return
        with self._prune_lock:
            files = []
            total = 0
            for path in self.cache_dir.iterdir():
                if not path.is_file() or path.suffix.casefold() not in {".webp", ".png", ".miss"}:
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if path.suffix.casefold() == ".miss" and time.time() - stat.st_mtime >= MISS_CACHE_SECONDS:
                    try:
                        path.unlink()
                    except OSError:
                        pass
                    continue
                files.append((stat.st_mtime, stat.st_size, path))
                total += stat.st_size
            if total <= self.max_cache_bytes:
                return
            target = int(self.max_cache_bytes * 0.85)
            for _mtime, size, path in sorted(files):
                try:
                    path.unlink()
                    total -= size
                except OSError:
                    continue
                if total <= target:
                    break

    def _extract(self, source: Path) -> Image.Image | None:
        extension = source.suffix.lower()
        try:
            if extension in IMAGE_EXTENSIONS:
                with Image.open(source) as image:
                    return image.copy()
            if extension == ".pdf":
                return self._extract_pdf(source, self.size)
            if extension == ".epub":
                return self._extract_epub(source)
            if extension == ".cbz":
                return self._extract_cbz(source)
        except (
            ImportError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            ElementTree.ParseError,
            UnidentifiedImageError,
            zipfile.BadZipFile,
        ):
            return None
        return None

    @staticmethod
    def _extract_pdf(source: Path, size=(120, 172)) -> Image.Image | None:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(str(source))
        try:
            if len(document) < 1:
                return None
            page = document[0]
            try:
                width, height = page.get_size()
                if width <= 0 or height <= 0:
                    return None
                # Decode only enough pixels for a crisp thumbnail, not a full
                # print-sized page (especially important for oversized PDFs).
                scale = min(1.2, min(size[0] / width, size[1] / height) * 2)
                bitmap = page.render(scale=scale)
                try:
                    return bitmap.to_pil().copy()
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            document.close()

    @staticmethod
    def _safe_archive_image(archive: zipfile.ZipFile, member: str) -> Image.Image | None:
        try:
            info = archive.getinfo(member)
        except KeyError:
            return None
        if info.file_size <= 0 or info.file_size > MAX_ARCHIVE_IMAGE_BYTES:
            return None
        with archive.open(info) as stream, Image.open(stream) as image:
            return image.copy()

    def _extract_cbz(self, source: Path) -> Image.Image | None:
        with zipfile.ZipFile(source) as archive:
            names = sorted(
                info.filename
                for info in archive.infolist()
                if not info.is_dir()
                and PurePosixPath(info.filename).suffix.lower() in IMAGE_EXTENSIONS
                and info.file_size <= MAX_ARCHIVE_IMAGE_BYTES
            )
            if not names:
                return None
            return self._safe_archive_image(archive, names[0])

    def _extract_epub(self, source: Path) -> Image.Image | None:
        with zipfile.ZipFile(source) as archive:
            container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            if rootfile is None:
                return None
            opf_path = rootfile.attrib.get("full-path", "")
            if not opf_path:
                return None
            package = ElementTree.fromstring(archive.read(opf_path))
            manifest = {
                node.attrib.get("id", ""): node
                for node in package.findall(".//{*}manifest/{*}item")
            }
            cover_id = ""
            for meta in package.findall(".//{*}metadata/{*}meta"):
                if meta.attrib.get("name") == "cover":
                    cover_id = meta.attrib.get("content", "")
                    break
            candidate = manifest.get(cover_id)
            if candidate is None:
                candidate = next(
                    (
                        node
                        for node in manifest.values()
                        if "cover-image" in node.attrib.get("properties", "").split()
                    ),
                    None,
                )
            if candidate is None:
                candidate = next(
                    (
                        node
                        for node in manifest.values()
                        if "cover" in node.attrib.get("id", "").casefold()
                        and PurePosixPath(node.attrib.get("href", "")).suffix.lower() in IMAGE_EXTENSIONS
                    ),
                    None,
                )
            if candidate is None:
                return None
            base = posixpath.dirname(opf_path)
            member = posixpath.normpath(posixpath.join(base, candidate.attrib.get("href", "")))
            if member.startswith(("../", "/")):
                return None
            return self._safe_archive_image(archive, member)
