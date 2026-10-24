import html
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .cancellation import OperationCancelled
from .reader_worker import isolated

MAX_TEXT_CHARS = 2_000_000
MAX_XML_BYTES = 12_000_000
MAX_PROCESS_BYTES = 8_000_000


def _read_prefix(path, limit, *, reject_excess=False):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if reject_excess and len(data) > limit:
        raise ValueError("El documento supera el límite de lectura segura")
    return data[:limit]


def _xml_root(data):
    if len(data) > MAX_XML_BYTES or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("XML demasiado grande o con entidades no permitidas")
    return ET.fromstring(data)


@dataclass
class ReaderResult:
    text: str = ""
    metadata: dict = field(default_factory=dict)
    method: str = ""
    error: str = ""
    external_dependency: str = ""

    def as_dict(self):
        return asdict(self)


def _xml_text(data, max_chars=MAX_TEXT_CHARS):
    root = _xml_root(data)
    chunks = []
    total = 0
    for node in root.iter():
        value = (node.text or "").strip()
        if value:
            chunks.append(value)
            total += len(value) + 1
            if total >= max_chars:
                break
    return "\n".join(chunks)[:max_chars]


def _read_zip_member(archive, name):
    try:
        info = archive.getinfo(name)
        if info.file_size > MAX_XML_BYTES:
            raise ValueError("La entrada ZIP supera el límite de lectura segura")
        with archive.open(info) as stream:
            data = stream.read(MAX_XML_BYTES + 1)
        if len(data) > MAX_XML_BYTES:
            raise ValueError("La entrada ZIP expandida supera el límite")
        return data
    except (KeyError, OSError):
        return b""


def _docx(path):
    with zipfile.ZipFile(path) as archive:
        text = _xml_text(_read_zip_member(archive, "word/document.xml"))
        metadata = {}
        core = _read_zip_member(archive, "docProps/core.xml")
        if core:
            root = _xml_root(core)
            for node in root.iter():
                name = node.tag.rsplit("}", 1)[-1]
                if name in {"title", "creator", "subject", "language"} and (node.text or "").strip():
                    metadata[name] = node.text.strip()
        return ReaderResult(text, metadata, "docx_xml").as_dict()


def _odt(path):
    with zipfile.ZipFile(path) as archive:
        text = _xml_text(_read_zip_member(archive, "content.xml"))
        metadata = {}
        meta = _read_zip_member(archive, "meta.xml")
        if meta:
            root = _xml_root(meta)
            for node in root.iter():
                name = node.tag.rsplit("}", 1)[-1]
                if name in {"title", "creator", "language", "description"} and (node.text or "").strip():
                    metadata[name] = node.text.strip()
        return ReaderResult(text, metadata, "odt_xml").as_dict()


def _rtf(path):
    raw = _read_prefix(path, 8_000_000)
    source = raw.decode("latin-1", errors="replace")
    source = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", errors="replace"), source)
    source = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), source)
    source = re.sub(r"\\(?:par|line)\b", "\n", source)
    source = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", source)
    source = re.sub(r"[{}]", "", source)
    text = html.unescape(source)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return ReaderResult(text[:MAX_TEXT_CHARS], {}, "rtf_parser").as_dict()


def _fb2(path):
    raw = _read_prefix(path, MAX_XML_BYTES, reject_excess=True)
    return ReaderResult(_xml_text(raw), {}, "fb2_xml").as_dict()


def _plain(path):
    raw = _read_prefix(path, 4_000_000)
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return ReaderResult(raw.decode(encoding)[:MAX_TEXT_CHARS], {}, f"text_{encoding}").as_dict()
        except UnicodeError:
            continue
    return ReaderResult(error="No se pudo decodificar el texto", method="text").as_dict()


def _run_bounded(command, *, timeout, cancellation=None, cwd=None):
    if cancellation:
        cancellation.raise_if_cancelled()
    process = subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=False, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()

    def drain(stream, target, limit):
        try:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                remaining = limit - len(target)
                target.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
                    process.kill()
                    break
        except (OSError, ValueError):
            pass

    readers = [threading.Thread(target=drain, args=(stream, target, limit), daemon=True)
               for stream, target, limit in zip((process.stdout, process.stderr), buffers,
                                                (MAX_PROCESS_BYTES, 500_000))]
    for reader in readers:
        reader.start()
    try:
        with cancellation.track_process(process) if cancellation else nullcontext():
            process.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise RuntimeError(f"El lector externo superó {timeout} segundos") from exc
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        for reader in readers:
            reader.join(timeout=2)
        process.stdout.close()
        process.stderr.close()
    if cancellation:
        cancellation.raise_if_cancelled()
    if overflow.is_set():
        raise RuntimeError("La salida del lector externo supera el límite seguro")
    stdout, stderr = (bytes(data) for data in buffers)
    if process.returncode != 0:
        if cancellation:
            cancellation.raise_if_cancelled()
        message = stderr.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(message or f"El lector externo terminó con código {process.returncode}")
    return stdout[:8_000_000]


def _djvu(path, timeout, cancellation):
    executable = shutil.which("djvutxt")
    if not executable:
        return ReaderResult(method="djvu", error="DjVuLibre/djvutxt no está instalado", external_dependency="djvutxt").as_dict()
    raw = _run_bounded([executable, str(path)], timeout=timeout, cancellation=cancellation)
    return ReaderResult(raw.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS], {}, "djvutxt").as_dict()


def _legacy_doc(path, timeout, cancellation):
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if not executable:
        return ReaderResult(method="doc", error="LibreOffice no está instalado", external_dependency="libreoffice").as_dict()
    with tempfile.TemporaryDirectory(prefix="myl_doc_") as temp:
        _run_bounded(
            [executable, "--headless", "--convert-to", "txt:Text", "--outdir", temp, str(path)],
            timeout=timeout, cancellation=cancellation,
        )
        output = Path(temp) / f"{path.stem}.txt"
        if not output.exists():
            raise RuntimeError("LibreOffice no produjo el texto esperado")
        return _plain(output) | {"method": "libreoffice_doc"}


@isolated('document', timeout=50)
def extract_document(path, *, timeout=45, cancellation=None):
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            return _docx(path)
        if suffix == ".odt":
            return _odt(path)
        if suffix == ".rtf":
            return _rtf(path)
        if suffix == ".fb2":
            return _fb2(path)
        if suffix == ".txt":
            return _plain(path)
        if suffix == ".djvu":
            return _djvu(path, timeout, cancellation)
        if suffix == ".doc":
            return _legacy_doc(path, timeout, cancellation)
        return ReaderResult(method="unsupported", error=f"Formato no soportado por lector estructurado: {suffix}").as_dict()
    except OperationCancelled:
        raise
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        ET.ParseError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ) as exc:
        return ReaderResult(method=suffix.lstrip("."), error=str(exc)).as_dict()
