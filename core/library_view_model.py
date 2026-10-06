"""Pure helpers for presenting and filtering the durable library index."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _human_size(size: object) -> str:
    try:
        value = max(0, int(size or 0))
    except (TypeError, ValueError):
        value = 0
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


FAVORITE_TAGS = {"favorito", "favorita", "favoritos", "favorite", "favourite", "favori", "收藏"}


def item_is_favorite(item: dict) -> bool:
    """Accept current boolean flags and older favorite-as-tag records."""
    for key in ("favorite", "favorito", "is_favorite"):
        value = item.get(key)
        if isinstance(value, str):
            if value.strip().casefold() in {"1", "true", "yes", "si", "sí", "oui", "是"}:
                return True
        elif bool(value):
            return True
    tags = item.get("tags_mostrar", item.get("tags", [])) or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",") if part.strip()]
    return any(_fold(tag) in FAVORITE_TAGS for tag in tags)


def cover_grid_positions(item_count: int, columns: int) -> list[tuple[int, int]]:
    """Return bounded cover positions without creating or destroying widgets."""
    safe_columns = max(1, int(columns))
    return [divmod(index, safe_columns) for index in range(max(0, int(item_count)))]


def display_item(item: dict) -> dict:
    """Return stable display fields without changing the index record."""
    path = Path(str(item.get("ruta") or item.get("nombre") or ""))
    name = str(item.get("nombre") or path.name or "Sin título")
    stem = Path(name).stem.replace("_", " ").strip() or "Sin título"
    author = str(item.get("autor") or "").strip()
    title = stem

    parts = [part.strip() for part in re.split(r"\s+-\s+", stem) if part.strip()]
    if len(parts) >= 2:
        if author and _fold(parts[0]) == _fold(author):
            title = " - ".join(parts[1:])
        elif author and _fold(parts[-1]) == _fold(author):
            title = " - ".join(parts[:-1])
        elif not author:
            # The application's canonical filename is "Author - Title".
            # Keep the full remainder as the title so subtitles containing a
            # dash are not mistaken for an author.
            author = parts[0]
            title = " - ".join(parts[1:])

    title = str(item.get("titulo") or item.get("titulo_real") or title).strip()
    extension = str(item.get("extension") or path.suffix or "").lower()
    isbn = re.sub(r"[^0-9Xx]", "", str(item.get("isbn") or "")).upper()
    if not isbn:
        match = re.search(r"\[\s*((?:97[89][\s-]*)?\d(?:[\s-]*\d){8,11}[\s-]*[\dXx])\s*\]", name)
        if match:
            isbn = re.sub(r"[^0-9Xx]", "", match.group(1)).upper()
    if len(isbn) not in {10, 13}:
        isbn = ""
    cover_url = str(item.get("cover_url") or "").strip()
    if not cover_url and isbn:
        cover_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false"
    tags = item.get("tags") or []
    if isinstance(tags, str):
        tags = [part.strip() for part in tags.split(",") if part.strip()]
    displayed = {
        **item,
        "ruta": str(item.get("ruta") or path),
        "nombre": name,
        "titulo": title,
        "autor_mostrar": author or "Autor desconocido",
        "formato": extension.lstrip(".").upper() or "ARCHIVO",
        "tamano_mostrar": _human_size(item.get("tamano_bytes")),
        "isbn": isbn,
        "cover_url": cover_url,
        "serie_mostrar": str(item.get("serie") or item.get("series") or "").strip(),
        "idioma_mostrar": str(item.get("idioma") or item.get("language") or "").strip(),
        "editorial_mostrar": str(item.get("editorial") or item.get("publisher") or "").strip(),
        "anio_mostrar": str(item.get("anio") or item.get("year") or "").strip(),
        "edicion_mostrar": str(item.get("edicion") or item.get("edition") or "").strip(),
        "tags_mostrar": tags,
        "confianza_mostrar": item.get("confianza_global", item.get("confianza", "")),
    }
    displayed["favorite_mostrar"] = item_is_favorite(displayed)
    return displayed


class LibraryViewIndex:
    """Prepared, immutable view of catalog rows for interactive filtering.

    Normalizing every field on every keystroke made search scale linearly with
    a large constant. This index pays that cost once when the catalog object is
    replaced, then reuses folded search text and sort keys.
    """

    def __init__(self, items) -> None:
        prepared: list[dict[str, Any]] = []
        authors: set[str] = set()
        formats: set[str] = set()
        missing_author = 0
        for raw in items or []:
            item = display_item(dict(raw))
            author_folded = _fold(item["autor_mostrar"])
            format_folded = _fold(item["formato"])
            item["_view_format_folded"] = format_folded
            item["_view_sort_key"] = (
                _fold(item["titulo"]),
                author_folded,
                _fold(item["ruta"]),
            )
            item["_view_search_folded"] = _fold(
                " ".join(
                    [
                        item["titulo"],
                        item["autor_mostrar"],
                        item["nombre"],
                        item["formato"],
                        item["ruta"],
                        item["serie_mostrar"],
                        item["idioma_mostrar"],
                        item["editorial_mostrar"],
                        item["isbn"],
                        " ".join(str(tag) for tag in item["tags_mostrar"]),
                    ]
                )
            )
            prepared.append(item)
            if item["autor_mostrar"] == "Autor desconocido":
                missing_author += 1
            else:
                authors.add(author_folded)
            if item["formato"]:
                formats.add(item["formato"])

        self._items = sorted(prepared, key=lambda item: item["_view_sort_key"])
        self.formats = tuple(sorted(formats))
        self.stats = {
            "books": len(prepared),
            "authors": len(authors),
            "formats": len(formats),
            "missing_author": missing_author,
        }

    def filter(self, query: str = "", extension: str = "all") -> list[dict]:
        query_folded = _fold(query)
        extension_folded = _fold(extension).lstrip(".")
        filter_extension = extension_folded not in {"", "all", "todos"}
        return [
            item
            for item in self._items
            if (not filter_extension or item["_view_format_folded"] == extension_folded)
            and (not query_folded or query_folded in item["_view_search_folded"])
        ]


def provenance_lines(item: dict) -> list[str]:
    """Return short, human-readable provenance lines for the details pane."""
    provenance = item.get("provenance") or item.get("procedencia") or {}
    evidence = item.get("evidencias") or []
    lines = []
    if isinstance(provenance, dict):
        for field, value in provenance.items():
            if isinstance(value, dict):
                source = value.get("source") or value.get("fuente") or ""
                confidence = value.get("confidence", value.get("confianza", ""))
                summary = str(source or value.get("value") or value.get("valor") or "").strip()
                if confidence not in {"", None}:
                    summary = f"{summary} · {confidence}%" if summary else f"{confidence}%"
            elif isinstance(value, (list, tuple)):
                summary = ", ".join(str(part) for part in value[:3] if part not in {"", None})
            else:
                summary = str(value or "").strip()
            if summary:
                lines.append(f"{field}: {summary}")
    if not lines and isinstance(evidence, list):
        for entry in evidence[:4]:
            if not isinstance(entry, dict):
                continue
            field = entry.get("field") or entry.get("campo") or "dato"
            source = entry.get("source") or entry.get("fuente") or "local"
            confidence = entry.get("confidence", entry.get("confianza", ""))
            suffix = f" · {confidence}%" if confidence not in {"", None} else ""
            lines.append(f"{field}: {source}{suffix}")
    return lines


def filter_items(items, query: str = "", extension: str = "all") -> list[dict]:
    """Filter and sort index records for either the cover or table view."""
    return LibraryViewIndex(items).filter(query, extension)


def library_stats(items) -> dict:
    displayed = [display_item(dict(item)) for item in (items or [])]
    authors = {
        _fold(item["autor_mostrar"])
        for item in displayed
        if item["autor_mostrar"] != "Autor desconocido"
    }
    formats = {item["formato"] for item in displayed if item["formato"]}
    missing_author = sum(item["autor_mostrar"] == "Autor desconocido" for item in displayed)
    return {
        "books": len(displayed),
        "authors": len(authors),
        "formats": len(formats),
        "missing_author": missing_author,
    }
