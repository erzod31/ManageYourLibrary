"""Opt-in binary update channel. It never scans or modifies a book library."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

PRODUCT = "ManageYourLibrary"
APP_ID = "{A4A5DE08-8644-4D67-B03E-271515180F7D}"
MAC_BUNDLE_ID = "org.manageyourlibrary.desktop"
DEFAULT_REPOSITORY = "erzod31/ManageYourLibrary"
MAX_PACKAGE_BYTES = 1024**3
MAX_JSON_BYTES = 2 * 1024**2
TRUSTED_HOSTS = {"api.github.com", "github.com", "release-assets.githubusercontent.com",
                 "objects.githubusercontent.com", "github-releases.githubusercontent.com"}
ASSET_PATTERNS = {
    "windows-installer-x64": r"ManageYourLibrary-(\d+\.\d+\.\d+)-Setup-x64\.exe",
    "windows-portable-x64": r"ManageYourLibrary-(\d+\.\d+\.\d+)-Windows-x64-portable\.zip",
    "linux-x64": r"ManageYourLibrary-(\d+\.\d+\.\d+)-Linux-x64\.tar\.gz",
    "macos-arm64": r"ManageYourLibrary-(\d+\.\d+\.\d+)-macOS-arm64\.zip",
    "macos-x64": r"ManageYourLibrary-(\d+\.\d+\.\d+)-macOS-x64\.zip",
}


class UpdateError(RuntimeError):
    pass


class UpdateCancelled(UpdateError):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d{0,5})\.(?:0|[1-9]\d{0,5})\.(?:0|[1-9]\d{0,5})", value):
        raise UpdateError("La versión del paquete no es válida.")
    return tuple(map(int, value.split(".")))


def repository_name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", value):
        raise UpdateError("Usa el repositorio GitHub con el formato propietario/proyecto.")
    return value


def trusted_url(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in TRUSTED_HOSTS or parsed.username or
                parsed.password or parsed.port not in (None, 443) or parsed.fragment):
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise UpdateError("El canal redirigió a un origen de descarga no autorizado.") from exc
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        trusted_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_url(url):
    trusted_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "ManageYourLibrary binary-updater/1",
                                                 "Accept": "application/vnd.github+json"})
    return urllib.request.build_opener(SafeRedirect()).open(request, timeout=15)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    from .index_store import guardar_json
    guardar_json(Path(path), value)


@dataclass(frozen=True)
class UpdateOffer:
    product: str
    version: str
    platform: str
    name: str
    url: str
    size: int
    sha256: str
    repository: str
    tag: str

    def validate(self, current_version, expected_platform):
        if self.product != PRODUCT or self.platform != expected_platform or expected_platform not in ASSET_PATTERNS:
            raise UpdateError("El paquete pertenece a otro producto o plataforma.")
        if version_tuple(self.version) <= version_tuple(current_version):
            raise UpdateError("No se permite instalar una versión anterior o igual.")
        match = re.fullmatch(ASSET_PATTERNS[expected_platform], self.name)
        if not match or match.group(1) != self.version:
            raise UpdateError("El nombre y la versión del paquete no coinciden.")
        repository_name(self.repository)
        if not re.fullmatch(r"v" + re.escape(self.version) + r"(?:-native\.[1-9]\d*)?", self.tag):
            raise UpdateError("La etiqueta de publicación no corresponde a la versión.")
        expected = f"https://github.com/{self.repository}/releases/download/{self.tag}/{self.name}"
        if self.url != expected:
            raise UpdateError("La descarga no pertenece a la publicación configurada.")
        trusted_url(self.url)
        if (isinstance(self.size, bool) or not isinstance(self.size, int) or not 0 < self.size <= MAX_PACKAGE_BYTES or
                not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)):
            raise UpdateError("Falta el tamaño o SHA-256 válido del paquete.")
        return self


class UpdateChannel:
    def __init__(self, repository=DEFAULT_REPOSITORY, *, opener=open_url):
        self.repository = repository_name(repository)
        self.opener = opener

    @property
    def source(self):
        return f"https://api.github.com/repos/{self.repository}/releases?per_page=30"

    def check(self, current_version, target):
        version_tuple(current_version)
        if target not in ASSET_PATTERNS:
            raise UpdateError("No hay paquete compatible con esta arquitectura.")
        with self.opener(self.source) as response:
            raw = response.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise UpdateError("La respuesta del canal supera el límite permitido.")
        try:
            releases = json.loads(raw)
            if not isinstance(releases, list):
                raise ValueError()
        except (ValueError, UnicodeError) as exc:
            raise UpdateError("El canal no devolvió una lista de publicaciones válida.") from exc
        available = []
        for release in releases:
            if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
                continue
            for asset in release.get("assets", []):
                if not isinstance(asset, dict) or asset.get("state") != "uploaded":
                    continue
                match = re.fullmatch(ASSET_PATTERNS[target], str(asset.get("name", "")))
                if match:
                    available.append((version_tuple(match.group(1)), str(release.get("published_at", "")), release, asset))
        if not available:
            return {"status": "no_package", "current": current_version, "available": None, "offer": None}
        _, _, release, asset = max(available, key=lambda row: row[:2])
        remote_version = re.fullmatch(ASSET_PATTERNS[target], asset["name"]).group(1)
        if version_tuple(remote_version) <= version_tuple(current_version):
            return {"status": "up_to_date", "current": current_version, "available": remote_version, "offer": None}
        digest = str(asset.get("digest") or "")
        offer = UpdateOffer(PRODUCT, remote_version, target, asset["name"], asset.get("browser_download_url", ""),
                            asset.get("size"), digest.removeprefix("sha256:"), self.repository, release.get("tag_name", ""))
        offer.validate(current_version, target)
        return {"status": "available", "current": current_version, "available": remote_version, "offer": offer}

    def download(self, offer, current_version, target, directory, *, cancelled=None, progress=None):
        offer.validate(current_version, target)
        if offer.repository != self.repository:
            raise UpdateError("El canal cambió después de buscar la actualización. Busca de nuevo.")
        cancelled = cancelled or threading.Event()
        progress = progress or (lambda received, total: None)
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / offer.name
        temporary = path.with_name(path.name + ".part")
        if path.is_file() and path.stat().st_size == offer.size and sha256(path) == offer.sha256:
            return path
        if shutil.disk_usage(folder).free < offer.size + 64 * 1024**2:
            raise UpdateError("Falta espacio libre para descargar con un margen de seguridad.")
        if temporary.exists():
            raise UpdateError("Ya hay una transferencia en esta sesión. Prepara otra descarga.")
        digest = hashlib.sha256()
        count, last_progress = 0, 0.0
        try:
            if cancelled.is_set():
                raise UpdateCancelled("Descarga cancelada.")
            with self.opener(offer.url) as response, temporary.open("xb") as out:
                length = response.headers.get("Content-Length")
                if length is not None and (not length.isdigit() or int(length) != offer.size):
                    raise UpdateError("El tamaño anunciado no coincide con el canal.")
                while chunk := response.read(64 * 1024):
                    if cancelled.is_set():
                        raise UpdateCancelled("Descarga cancelada; la aplicación actual se conserva.")
                    count += len(chunk)
                    if count > offer.size:
                        raise UpdateError("El paquete supera el tamaño autorizado.")
                    out.write(chunk)
                    digest.update(chunk)
                    if time.monotonic() - last_progress >= .1:
                        progress(count, offer.size)
                        last_progress = time.monotonic()
                out.flush()
                os.fsync(out.fileno())
            if count != offer.size or digest.hexdigest() != offer.sha256:
                raise UpdateError("El paquete recibido está incompleto o su SHA-256 no coincide.")
            if cancelled.is_set():
                raise UpdateCancelled("Descarga cancelada.")
            os.replace(temporary, path)
            atomic_json(folder / "download.json", {"offer": asdict(offer), "verified": True})
            progress(count, offer.size)
            return path
        finally:
            if temporary.exists():
                temporary.unlink()  # Only this session's partial binary, never user books/state.


def process_platform():
    machine = platform.machine().lower()
    arch = "arm64" if machine in {"arm64", "aarch64"} else "x64" if machine in {"amd64", "x86_64"} else "unsupported"
    import sys
    if sys.platform == "win32":
        return "windows-portable-x64" if arch == "x64" else "unsupported"
    if sys.platform == "darwin":
        return "macos-" + arch
    return "linux-" + arch if sys.platform.startswith("linux") else "unsupported"
