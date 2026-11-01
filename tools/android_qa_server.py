"""Disposable TLS integration fixture, never the user's catalog or Tailscale config."""
import argparse
import io
import json
import os
import ssl
import sys
import threading
import time
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18443)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise SystemExit("QA root must be empty; existing data is never removed")
    for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        os.environ[name] = str(root / name)
    os.environ["MANAGE_YOUR_LIBRARY_OFFLINE"] = "1"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import library_core as core
    from core.mobile_access import DeviceAccess, MobileHttpServer
    from core.mobile_library import DesktopLibraryAdapter
    from PIL import Image, ImageDraw, ImageFont

    core.FINAL = root / "library"
    core.FINAL.mkdir()
    core.guardar_configuracion_operacion({"offline_mode": True})
    rows = []
    titles = ["El jardín invisible", "Mapas del silencio", "La ciudad de otro sol", "Cosas que dejamos atrás", "El eco de la marea", "Habitaciones propias"]
    authors = ["Clara Montes", "Diego Salazar", "Valeria Ríos", "Tomás Beltrán", "Lucía Ferrer", "Martina Vega"]
    colors = ["#42634b", "#4a6677", "#ae7949", "#6c615b", "#456671", "#5e5247"]
    for index, (title, author, color) in enumerate(zip(titles, authors, colors)):
        book = core.FINAL / f"{author} - {title}.epub"
        image = Image.new("RGB", (360, 520), color)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((14, 14, 345, 505), radius=10, outline="#d5c3a1", width=2)
        draw.text((32, 130), title.replace(" ", "\n", 2), font=ImageFont.load_default(size=29), fill="white")
        draw.text((32, 430), author, font=ImageFont.load_default(size=19), fill="#eee1cc")
        cover = io.BytesIO()
        image.save(cover, "PNG")
        with zipfile.ZipFile(book, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip")
            archive.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
            archive.writestr("book.opf", f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{title}</dc:title><dc:creator>{author}</dc:creator><dc:language>es</dc:language><meta name="cover" content="cover"/></metadata><manifest><item id="cover" href="cover.png" media-type="image/png" properties="cover-image"/><item id="text" href="text.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="text"/></spine></package>')
            archive.writestr("cover.png", cover.getvalue())
            archive.writestr("text.xhtml", f'<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>{title}</h1><p>{author}</p><p>Disposable synthetic QA fixture. No personal book.</p></body></html>')
        rows.append({"ruta": str(book), "nombre": book.name, "titulo": title, "autor": author,
                     "tamano_bytes": book.stat().st_size, "idioma": "es", "serie": "Horizontes" if index % 2 == 0 else "",
                     "tags": ["Novela"], "favorite": index == 2})
    core.guardar_indice({"archivos": rows})
    access = DeviceAccess(core.APP_DATA / "mobile/devices.json")
    adapter = DesktopLibraryAdapter(core)
    server = MobileHttpServer(("127.0.0.1", args.port), access, adapter)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(args.certificate, args.key)
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    ready = root / "ready.json"
    def codes():
        while True:
            ready.write_text(json.dumps({"url": f"https://10.0.2.2:{args.port}", "code": access.new_code()}), encoding="utf-8")
            time.sleep(90)
    threading.Thread(target=codes, daemon=True).start()
    try:
        server.serve_forever(poll_interval=.1)
    finally:
        server.server_close()
        adapter.close()


if __name__ == "__main__":
    main()
