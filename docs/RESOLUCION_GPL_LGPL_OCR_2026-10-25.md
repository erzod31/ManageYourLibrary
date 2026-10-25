# Resolución técnica de GPL/LGPL en el OCR nuevo

## Decisión y alcance

Se mantiene MIT para el código propio. No se compra una licencia comercial ni
se declara que Apache/MIT cubra JBIG-KIT. Se sustituye el conjunto antiguo por
una compilación controlada desde fuentes fijadas, sin las bibliotecas OCR
GPL/LGPL. Es una resolución por **eliminación de la dependencia del producto
nuevo**, no una regularización retroactiva de binarios ya entregados.

El [autor de JBIG-KIT](https://www.cl.cam.ac.uk/~mgk25/jbigkit/) describe sus vías
GPL y comercial. Borrar únicamente `libjbig-0.dll` no sirve: el TIFF antiguo la
importaba. Tampoco basta con copiar `COPYING` para dar por cumplida la GPL/LGPL.
La auditoría anterior permanece intacta como evidencia de los binarios viejos.

## Implementación

- `tools/ocr_source_lock.json`: Tesseract 5.5.3, Leptonica 1.87.0, libpng 1.6.59
  y zlib 1.3.2, con URLs versionadas/commits y SHA-256. No `latest` durante build.
- Enlace estático de esas cuatro bibliotecas, sin TIFF/JBIG, JPEG/WebP/OpenJPEG
  de Leptonica, curl, archive, OpenMP, entrenamiento, ScrollView, Pango ni GLib.
- Windows: MSVC `/MT`, sin DLL de GCC/MinGW. Los términos Microsoft siguen
  aplicándose al runtime del compilador; no se lo etiqueta MIT.
- Linux/macOS: solo dependencias de la línea base del sistema para el CLI OCR;
  no se copian bibliotecas GPL/LGPL del sistema a este payload OCR.
- Se conservan `eng`, `spa`, `fra`, `nld`, `chi_sim` y `osd`, verificados contra
  el commit oficial `87416418657359cb625c412a48b6e1d6d41c29bd` de tessdata_fast.
- Se entregan fuentes completas, receta, comandos/cachés normalizados,
  licencias, autores y avisos por fichero. Los ejemplos/contrib no compilados
  conservan sus propias licencias dentro de las fuentes; no forman parte del CLI.
- El empaquetado Windows exige el inventario controlado y revisa imports PE;
  los builds nativos dejan de copiar OCR arbitrario de Homebrew/distribuciones.
- Se separa `ocr_libraries_profile: passed` del permiso global de redistribución.
  La puerta global no se abre automáticamente por pasar una prueba técnica.

Los 57 binarios antiguos y cuatro JAR de depuración se retiraron del árbol
actual, después de conservar una copia externa y verificar cada SHA-256 antes
de retirarlo. Los modelos, avisos históricos, libros y perfiles se preservan.
No se añade ningún ejecutable nuevo a Git.

## Funcionalidad y límites

El motor de la app ya prepara PNG mediante Pillow/PDFium. El helper de archivo
se ha ajustado para usar también esa ruta, sin entregar JPEG/TIFF directamente
al CLI. Se prueban PNG, JPG, JPEG, TIF, TIFF, BMP y WebP con originales intactos,
la carga conjunta de cinco idiomas y la salida TSV usada en el análisis visual.
El formato TIFF/JBIG depende de la capacidad del decodificador de imágenes de
la app; el CLI OCR nuevo **no** ofrece decodificación JBIG directa.

No se promete que un motor entrenado reconozca igual todos los libros; son
pruebas sintéticas de integración. El OCR sigue siendo local y cancelable.

## Reproducir sin tocar datos personales

Windows necesita Python 3.12, dependencias bloqueadas y Visual Studio 2022 Build
Tools con C++/CMake/Ninja. Desde un checkout limpio:

```text
python -B tools/build_permissive_ocr.py --output dist/ocr
python -B tools/verify_ocr_payload.py dist/ocr/payload
python -B tools/verify_ocr_functionality.py dist/ocr/payload --output dist/ocr-formats.json
python -B tools/run_tests.py
BUILD_EXE.bat
```

`BUILD_EXE.bat` utiliza el builder Windows existente, que prepara el OCR si falta.
Para una salida externa ya verificada, definir `MANAGE_YOUR_LIBRARY_OCR_DIR`.
No se sobrescribe una salida existente; `--resume` permite continuar una
compilación interrumpida solo si sus fuentes extraídas siguen siendo idénticas.

En Linux/macOS: `python3 tools/bundle_native_ocr.py`, seguido del builder nativo
existente. El workflow de la rama de pruebas construye y prueba cada arquitectura;
los resultados se registran cuando terminan. Un éxito Windows no valida Unix.

## Lo que esta corrección no regulariza

Las releases anteriores y los objetos antiguos de Git contienen el conjunto
auditado. Se conservan sin una nueva declaración de conformidad y no deben
reutilizarse como base de una publicación nueva. Retirar el fichero de `HEAD`
no borra sus obligaciones históricas ni las copias ya descargadas.

No se reescribe historial, elimina una release ni publica una versión sin una
instrucción específica. Para regularizar redistribuciones anteriores harían falta
las fuentes correspondientes exactas y demás condiciones del conjunto entregado,
o una solución de licencias acordada con sus titulares. Esta corrección tampoco
certifica toda dependencia de Python/Tk/PDFium ni sustituye asesoramiento jurídico.

## Resultados de esta revisión

Windows final, fuente limpia `52c986b3904eaf4d11767483cc31388e97f59d54`:

- 503 pruebas, correctas, dos omitidas por permisos de symlinks en Windows.
- Siete formatos y originales intactos; cinco idiomas cargados juntos y TSV.
- Runtime congelado: 5/5, con Tk 9.1, PDFium y OCR en el lector aislado.
- Primer uso congelado: 5/5, sin biblioteca ni peticiones automáticas.
- Puerta de rendimiento: catálogos sintéticos de 1.000, 10.000 y 50.000 registros.
- OCR de 3.315.712 bytes; únicamente importa `KERNEL32.dll`. Cero DLL en su
  payload y cero prefijos de rutas de perfil Windows en el CLI. Se comprobó
  realmente `/pathmap` con `/experimental:deterministic`, no solo su configuración.
- Aviso MIT de pefile conservado, además de las licencias de las bibliotecas OCR.
- Validador del paquete Windows ejecutado contra los bytes congelados: correcto.

SHA-256 del CLI OCR:
`65d98b046e5e8be1a5d73d07305277ad89f1d59edcf19959d69951c2cafc8be7`.
SHA-256 de la app congelada:
`f4fd156d10e555f8f978e2237f7305fc0f5a650397196f2d800c69904c70bf3a`.
Inventario OCR: 32 ficheros, incluidas fuentes, avisos y cachés de configuración.
[Evidencia estructurada Windows](validation_data_2026-10-25/ocr-replacement-windows.json).

Validación nativa completa de la misma receta OCR y código común, fuente
`d10f7d689227397894eb05ec010458eb5ddc1940`:
[run 40170858790](https://github.com/erzod31/ManageYourLibrary/actions/runs/40170858790).

| Destino | Job | Resultado |
| --- | --- | --- |
| Ubuntu 22.04 x64 | 121101454985 | Correcto: 503 pruebas, una omitida |
| macOS 15 ARM64 | 121101454986 | Correcto: 503 pruebas, una omitida |
| macOS 15 Intel x64 | 121101454878 | Correcto: 503 pruebas, una omitida |

Cada job construyó el OCR desde las fuentes fijadas, verificó formatos/TSV/modelos,
comprobó la API de accesibilidad y probó la aplicación congelada y su archivo
extraído (runtime y primer uso). `publish` fue **skipped**: no se publicó release.
Los paquetes nuevos no copian el OCR de la distribución ni de Homebrew.

La revisión Windows posterior solo añadió su aviso MIT de pefile; no cambió el
OCR ni el código nativo común. La fuente de `52c986b` también pasó los dos jobs
de [source validation](https://github.com/erzod31/ManageYourLibrary/actions/runs/40171422172).
Su repetición de builds nativos se lanzó en
[run 40171422171](https://github.com/erzod31/ManageYourLibrary/actions/runs/40171422171);
no se da por terminada hasta comprobar su resultado.

No se construyó ni instaló un instalador nuevo en esta revisión. No se validó
manualmente UI, voz/lector externo, firma comercial o notarización. El checkout
privado y sus cambios previos permanecen intactos. Los binarios históricos no
se declaran conformes; no se reescribió historia ni se modificó `main`.
