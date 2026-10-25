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

La primera compilación Windows controlada reconoció los siete formatos, cargó
los cinco idiomas juntos, produjo TSV y pasó los cinco checks de runtime con
Tk 9.1, PDFium y lectura en proceso aislado. La segunda compilación añade cachés
de configuración al inventario. Las evidencias finales de fuente, congelado y
CI se completan después de sus respectivas ejecuciones; no se reutilizan cifras
anteriores como si pertenecieran a esta revisión.
