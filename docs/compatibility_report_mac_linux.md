# Reporte de Compatibilidad macOS/Linux

Aplicacion: Manage Your Library  
Fecha de revision: 2026-05-24  

## Objetivo

Revisar la preparacion del proyecto para builds multiplataforma sin afirmar que
macOS o Linux funcionan si no se ejecutan en sus sistemas reales.

La app esta hecha en Python/Tkinter, se empaqueta con PyInstaller, usa `pypdfium2`
para renderizar PDFs y Tesseract local para OCR cuando corresponde.

## Que Se Reviso

- Rutas multiplataforma y uso de carpetas de datos de usuario.
- Recursos empaquetados con PyInstaller.
- Compatibilidad con `sys._MEIPASS`.
- Inclusion de `pypdfium2` y binarios PDFium.
- Deteccion de Tesseract y `tessdata`.
- Scripts de build separados para Windows, Linux y macOS.
- Riesgos de ejecucion en entornos Linux/macOS.
- Diferencias entre validar por auditoria de codigo y validar ejecutando un build real.

## Riesgos Encontrados

- Windows no puede validar de forma real un build macOS.
- Linux tampoco queda confirmado desde Windows si no se ejecuta en WSL, Docker o VM.
- `pypdfium2` necesita que PyInstaller incluya correctamente PDFium.
- Tesseract debe ser nativo para cada plataforma si se quiere distribuir como app completa.
- En macOS quedan riesgos externos al codigo: Gatekeeper, cuarentena, codesign y notarizacion.
- En Linux quedan riesgos externos al codigo: permisos de ejecucion, glibc, X11/Wayland y dependencias del sistema.

## Riesgos Corregidos o Reducidos

- La resolucion de recursos empaquetados usa rutas compatibles con PyInstaller.
- Se conserva soporte para `sys._MEIPASS` en recursos de interfaz y OCR.
- La deteccion de Tesseract contempla layouts portables:
  - `tesseract/tesseract.exe`
  - `tesseract/tesseract`
  - `tesseract/bin/tesseract`
- La deteccion de `tessdata` contempla:
  - `tesseract/tessdata`
  - `tesseract/share/tessdata`
- Los scripts de build Linux/macOS exigen runtime nativo de Tesseract para builds de release.
- Para builds de desarrollo en Linux/macOS se permite usar Tesseract del sistema solo si se define:

```text
MANAGE_YOUR_LIBRARY_ALLOW_SYSTEM_TESSERACT=1
```

- Los builds mantienen `--collect-all pypdfium2`, necesario para incluir PDFium.
- Los outputs de build estan separados por plataforma:
  - `dist/windows/`
  - `dist/linux/`
  - `dist/macos/`

## Estado Windows

Windows es el entorno principal probado durante la revision.

Se confirmo por ejecucion real:

- build Windows con PyInstaller correcto;
- `pypdfium2` incluido correctamente;
- PDFium disponible dentro del ejecutable;
- Tesseract empaquetado en el build Windows;
- `tessdata` disponible dentro del build Windows.

## Estado Linux

Linux queda preparado para build real en Linux, WSL, Docker o VM.

No debe considerarse validado hasta ejecutar el build en un entorno Linux real.

Puntos a confirmar en Linux:

- permisos `chmod +x`;
- arranque de la app;
- inclusion real de PDFium;
- inclusion o disponibilidad de Tesseract nativo;
- disponibilidad de `tessdata`;
- comportamiento con X11/Wayland;
- compatibilidad glibc de la distribucion destino.

## Estado macOS

macOS debe validarse en macOS real.

Opciones validas:

- Mac fisico;
- Mac mini remoto;
- GitHub Actions `macos-latest`;
- runner macOS propio.

No es correcto afirmar compatibilidad macOS solo desde Windows.

Puntos a confirmar en macOS:

- estructura `.app`, si se genera una app bundle;
- permisos de ejecucion;
- inclusion real de PDFium;
- Tesseract nativo y `tessdata`;
- comportamiento de Gatekeeper/cuarentena;
- codesign y notarizacion si se distribuye publicamente;
- arquitectura arm64/x86_64 segun destino.

## Que Se Confirmo Por Auditoria

- El proyecto usa rutas portables en los puntos principales revisados.
- Los recursos de app se resuelven con compatibilidad PyInstaller.
- OCR mantiene deteccion portable de Tesseract.
- Los builds de Linux/macOS no dependen silenciosamente de Tesseract del sistema para release.
- `pypdfium2` sigue contemplado en los scripts de build.
- La infraestructura temporal de pruebas fue retirada del proyecto final.

## Que Se Confirmo Por Ejecucion Real

- El build Windows fue generado correctamente.
- El ejecutable Windows empaquetado pudo cargar recursos, PDFium y Tesseract durante la revision.
- La compilacion Python de archivos principales fue correcta.
- Las dependencias Python no mostraron conflictos con `pip check`.

## Pendiente

- Ejecutar build Linux en Linux real.
- Ejecutar build macOS en macOS real.
- Revisar codesign/notarizacion si se distribuye macOS fuera de uso privado.
- Probar instalacion en equipos limpios por plataforma.
- Probar una pequena biblioteca real de libros en cada sistema operativo.

## Recomendaciones Finales

- Construir cada plataforma en su propio sistema operativo.
- No distribuir builds Linux/macOS sin prueba real en esos sistemas.
- Mantener Tesseract por plataforma dentro de `platforms/<sistema>/tesseract/` para releases completas.
- No subir `build/`, `dist/`, logs ni temporales al repositorio.
- Mantener el reporte como referencia de compatibilidad, no como sustituto de pruebas reales.


