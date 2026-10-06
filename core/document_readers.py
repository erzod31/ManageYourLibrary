import html
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .cancellation import OperationCancelled

MAX_TEXT_CHARS = 2_000_000


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
    root = ET.fromstring(data)
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
        return archive.read(name)
    except (KeyError, OSError):
        return b""


def _docx(path):
    with zipfile.ZipFile(path) as archive:
        text = _xml_text(_read_zip_member(archive, "word/document.xml"))
        metadata = {}
        core = _read_zip_member(archive, "docProps/core.xml")
        if core:
            root = ET.fromstring(core)
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
            root = ET.fromstring(meta)
            for node in root.iter():
                name = node.tag.rsplit("}", 1)[-1]
                if name in {"title", "creator", "language", "description"} and (node.text or "").strip():
                    metadata[name] = node.text.strip()
        return ReaderResult(text, metadata, "odt_xml").as_dict()


def _rtf(path):
    raw = path.read_bytes()[:8_000_000]
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
    raw = path.read_bytes()[:12_000_000]
    return ReaderResult(_xml_text(raw), {}, "fb2_xml").as_dict()


def _plain(path):
    raw = path.read_bytes()[:4_000_000]
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return ReaderResult(raw.decode(encoding)[:MAX_TEXT_CHARS], {}, f"text_{encoding}").as_dict()
        except UnicodeError:
            continue
    return ReaderResult(error="No se pudo decodificar el texto", method="text").as_dict()


def _run_bounded(command, *, timeout, cancellation=None, cwd=None):
    process = subprocess.Popen(
        command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=False, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    try:
        if cancellation:
            with cancellation.track_process(process):
                stdout, stderr = process.communicate(timeout=timeout)
        else:
            stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        process.communicate()
        raise RuntimeError(f"El lector externo superó {timeout} segundos") from exc
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
