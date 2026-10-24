# Validación Windows de la compilación de desarrollo

Esta evidencia corresponde a la rama local `codex/audit-optimizations`, no a los
activos publicados de 0.5.3. La versión interna continúa siendo 0.5.3; no se ha
asignado ni publicado un número de release nuevo.

Las dos primeras secciones conservan la evidencia de la **primera iteración**.
La sección «Cierre local» al final registra la compilación actual; las huellas y
resultados históricos anteriores no se presentan como si correspondieran a ella.

## Interacción medida

Windows 11, Python 3.12.10, 50.000 registros sintéticos, cien muestras por operación.
Las mediciones de persistencia y ventana se ejecutaron secuencialmente.

| Operación | Mediana | p95 |
| --- | ---: | ---: |
| Refresco de portadas | 12,45 ms | 16,77 ms |
| Página siguiente | 21,45 ms | 26,19 ms |
| Página anterior | 19,89 ms | 25,68 ms |
| Recolocar tarjetas | 0,22 ms | 0,30 ms |
| Llamada a mover división | 0,03 ms | 0,03 ms |
| Renderizar página de tabla | 7,72 ms | 9,97 ms |
| Volver a portadas | 16,01 ms | 20,96 ms |
| Tema | 53,37 ms | 60,56 ms |
| Selección | 4,76 ms | 5,78 ms |
| Despachar favorito al trabajador | 4,02 ms | 4,96 ms |
| Favorito hasta actualizar pantalla | 103,61 ms | 126,69 ms |

La ventana mantuvo 30 tarjetas y 30 filas de tabla, con cero errores de callback.
RSS 317,75 MiB; pico 321,50 MiB. CPU del proceso 98,69 s durante 136,50 s de
interacción. Construcción síncrona del escenario de prueba: 3.878,22 ms; no es el
tiempo de la pantalla de carga asíncrona de `main`.

Máximo entre latidos durante interacción: **194,90 ms**; durante arranque,
371,54 ms. Por tanto, no se cumple todavía el objetivo de ausencia de pausas
superiores a 50 ms ni se acredita una interfaz de 60 fotogramas por segundo.
La medición no incluye extracción de todas las portadas en frío ni OCR de fondo.

La geometría pasó los 12 escenarios de tamaño/escala Tk y cinco comprobaciones
de comandos de filtros y previsualización. Es una prueba de widgets, no una
certificación de DPI del sistema o de lector de pantalla.

## Compilación

Compilación completada el 24 de octubre de 2026 mediante
`platforms/windows/BUILD_WINDOWS.bat`, en un entorno y destino nuevos. Los activos
publicados y la carpeta de distribución anterior se conservaron. Python 3.12.10,
PyInstaller 6.21.0, hooks 2026.6, dependencias de `requirements.lock` instaladas con
verificación de hashes. No incluye PySide6 ni el prototipo Qt.

- Base Git: `a7304c6dee8474f6e538f775db655eccf6be4800`, **árbol con cambios locales**.
- Huella de los 234 archivos de entrada:
  `5D2481A2E305EDEE5D908E79D3DB5C696DCD76B97B338D523C047967C62D1A6D`.
- `ManageYourLibrary.exe`, 5.105.749 bytes, SHA-256:
  `F6B157239448BC31CE105B60EE6F5855E59B82F15324CBBECF8C7ED842C7D0AF`.
- Carpeta completa: 1.235 archivos, 222.753.423 bytes. El ejecutable necesita el
  resto de esa carpeta; no es un binario autónomo ni un instalador.

| Comprobación | Resultado |
| --- | --- |
| Suite dentro del script de compilación | 452 pruebas, OK, 2 omitidas; 9,722 s |
| Smoke de fuentes y puerta de rendimiento | Pasaron |
| Smoke del ejecutable congelado | Pasó; política `identity_v12_independent_evidence` |
| Tk incluido | Pasó |
| Presencia de los cinco idiomas OCR incluidos | Pasó |
| OCR de imagen y PDF sintéticos en inglés | Pasó usando el runtime incluido |
| Primer uso congelado | Cinco controles pasaron: valores limpios, biblioteca vacía, sin trabajos automáticos, sin red automática y estado nuevo |
| Huella actual y hash del ejecutable | Coinciden con el manifiesto |
| Validador de contenido del paquete | Pasó, sin los archivos de perfil, libros o cachés que rechaza la política |
| Instalación, actualización y desinstalación reales | No ejecutadas |
| Firma de código | No realizada |

Los informes congelados registran `frozen: true`. El chequeo de runtime se creó a
las 20:40:28 UTC y el de primer uso a las 20:40:30 UTC. Ambos usan datos sintéticos,
no una biblioteca personal. No prueban todos los formatos ni todos los idiomas OCR.
El empaquetador informó importaciones opcionales ausentes, incluidas extensiones
de formatos/imágenes y criptografía; no se presenta soporte verificado para esas
capacidades opcionales.

Se dejó la carpeta de desarrollo fuera del repositorio. No se creó instalador
nuevo, ZIP de release, commit, tag o publicación. Para probarla, usar un perfil
separado mediante `--profile`, siguiendo las
[precauciones de migración](IMPLEMENTACION_Y_VALIDACION_2026-10-24.md#probar-sin-comprometer-el-perfil-habitual).

## Cierre local: código y mediciones actuales

La suite dentro del último build ejecutó **478 pruebas en 12,549 s: OK, dos
omitidas** por permisos de enlaces simbólicos. Ruff `E9,F63,F7,F82`, `git diff
--check` y `pip check` pasaron. `pip-audit` sobre el lock fijado no encontró avisos
conocidos; no auditó las DLL nativas del OCR ni certifica seguridad universal.

La sonda final pasó 12 geometrías (tres tamaños, cuatro escalas Tk) y nueve
comprobaciones de flujo, sin errores. Se comprobó visualmente el directorio de
autores, selección/Enter, libros del autor exacto y cambio de tema usando 400
registros sintéticos. No se usó una biblioteca personal ni un lector de pantalla.

### Interacción aceptada, 50.000 registros y 100 muestras

| Operación | Mediana | p95 | Máximo |
| --- | ---: | ---: | ---: |
| Refrescar portadas | 9,33 ms | 11,31 ms | 12,41 ms |
| Página siguiente | 15,75 ms | 17,30 ms | 20,15 ms |
| Página anterior | 15,42 ms | 17,12 ms | 20,09 ms |
| Recolocar tarjetas | 0,18 ms | 0,21 ms | 0,38 ms |
| Llamada a mover división | 0,02 ms | 0,02 ms | 0,04 ms |
| Tabla | 5,28 ms | 5,96 ms | 6,46 ms |
| Volver a portadas | 11,60 ms | 12,48 ms | 13,97 ms |
| Tema | 20,88 ms | 22,34 ms | 24,99 ms |
| Selección | 3,82 ms | 4,15 ms | 4,59 ms |
| Despachar favorito | 1,61 ms | 1,79 ms | 3,81 ms |
| Favorito hasta actualizar pantalla | 81,29 ms | 85,34 ms | 87,30 ms |

No hubo callbacks medidos superiores a 50 ms. El máximo entre latidos fue
**58,45 ms**, frente a 194,90 ms de la primera iteración: todavía no significa
que todos los fotogramas cumplan 50 ms ni 60 FPS. Construcción del escenario
3.614,31 ms; latido de arranque máximo 265,82 ms. RSS 322,41 MiB, pico 326,07 MiB;
71,98 s de CPU en 125,73 s de interacción. Se mantuvieron 30 tarjetas y 30 filas.

Se identificaron pausas de GC de generación 2 de 129–151 ms. El guard del catálogo
grande redujo ese recorrido en la muestra aceptada a una pausa de 11,02 ms.
GC de objetos nuevos y conteo de referencias siguieron activos; el guard se
deshace al cerrar. Los ensayos intermedios se conservan, incluidos los que aún
no activaban correctamente el guard. El archivo aceptado es
[`tk-ui-accepted.json`](validation_data_2026-10-24/tk-ui-accepted.json), **no**
el ensayo previo llamado `tk-ui-final.json`.

### Persistencia repetida, 100 ediciones por tamaño

| Registros | Guardado inicial | Mediana edición | p95 edición |
| --- | ---: | ---: | ---: |
| 1.000 | 96,49 ms | 11,43 ms | 12,44 ms |
| 10.000 | 1.346,05 ms | 12,61 ms | 14,34 ms |
| 50.000 | 9.126,15 ms | 15,10 ms | 19,07 ms |
| 100.000 | 21.062,80 ms | 18,58 ms | 26,11 ms |

Datos: [persistencia](validation_data_2026-10-24/persistence-completion.json),
[geometría](validation_data_2026-10-24/layout-completion.json),
[corpus](validation_data_2026-10-24/corpus-completion.json). La evaluación usa
12 casos de identidad y tres OCR sintéticos; no mide precisión poblacional ni
rendimiento de importación masiva sobre libros reales.

### Compilación actual

Se utilizaron los mismos entry points Windows, Python 3.12.10, PyInstaller 6.21.0,
hooks 2026.6 e Inno Setup 6.7.3. No se distribuye Qt.

- Base Git `a7304c6dee8474f6e538f775db655eccf6be4800`, árbol local sin commit.
- Huella de **250 archivos**:
  `557BA4CB1EE5E1029B9964DA68060DB97F2FB7ABAF160039BFCF8082E322697F`.
- EXE de **5.139.618 bytes**, SHA-256:
  `E501B1D1AE5FE68657D9B73487003CEC2AFDE6BE8F29A8DBFBFF96C2C40675C7`.
- Carpeta completa: **1.265 archivos, 223.162.897 bytes**.
- Runtime congelado registrado a las 21:32:12 UTC: Tk, cinco idiomas presentes,
  OCR de imagen/PDF y aislamiento correctos. El quinto chequeo ejecutó también
  OCR de PNG/PDF y portada PDF en los trabajadores congelados, no solo un ping.
- Primer uso vacío congelado correcto, sin operaciones ni red automáticas.
- Textos de licencia de Python, wheels y motor/modelos OCR incluidos; siguen
  pendientes la procedencia y obligaciones de todas las DLL del bundle heredado.
  El manifiesto registra `redistribution_review: not_complete`.

El empaquetador rechaza una release Windows normal mientras esa revisión no esté
cerrada. `--development` mantiene las comprobaciones de privacidad, hashes y
runtime, y añade una advertencia al ZIP y «development» a los nombres. No se ha
firmado ni publicado nada. Mac/Linux, DPI real, NVDA/VoiceOver y la revisión
completa de dependencias nativas siguen fuera de la validación realizada aquí.

### Instalación y paquetes comprobados

La repetición final de `tools/validate_windows_installation.py` pasó instalación
inicial, actualización y desinstalación silenciosas, por usuario, con **AppId y
carpetas temporales exclusivos de la prueba**. No creó accesos directos ni abrió
la instalación o el perfil habitual. Se conservaron byte a byte los cinco
archivos sintéticos de configuración, índice, planes, cuarentena e historia.
Se verificó el hash del EXE instalado antes/después y los cinco controles de
runtime desde la aplicación instalada. Al desinstalar se retiró el ejecutable
de prueba y siguió intacto el perfil sintético. La carpeta temporal de la prueba
se eliminó después; no contenía libros personales.

- EXE previo del escenario de actualización:
  `D1B96C77914367D42EF9774E1F5697BC1C65251661DB9D97E369AB91FDCC6674`.
- EXE actualizado: `E501B1D1AE5FE68657D9B73487003CEC2AFDE6BE8F29A8DBFBFF96C2C40675C7`.
- Informe local conservado fuera del repositorio:
  `completion-installation-licensed-2026-10-24.json`.

Esto **no** certifica el asistente interactivo, accesos directos, SmartScreen,
políticas de administrador ni una actualización real del perfil del propietario.
La licencia de redistribución y la firma siguen pendientes aunque el escenario
técnico de instalación pase.

El empaquetador validó la huella actual, los hashes, primer uso, runtime y
ausencia de los archivos personales/cachés prohibidos. El ZIP pasó el control
CRC completo. Artefactos locales, **solo desarrollo y sin publicar**:

| Archivo | Bytes | SHA-256 |
| --- | ---: | --- |
| `ManageYourLibrary-0.5.3-development-Windows-x64-portable.zip` | 98.352.654 | `8CB3D4679BDF4A3E7FE75EE02BE1B04081966220F8202B7DF09563B7811CC7E2` |
| `ManageYourLibrary-0.5.3-development-Setup-x64.exe` | 68.276.247 | `A5DAE530A62571361EB823E4FFC629ABB1384A6203D30B05AC49E1E1DE9750EC` |
| `build-manifest-0.5.3-development.json` | 3.523 | `17755E0C8089508AF7EB04295FA02186AF5B7A174DF49AA049CE3C7A463EAB67` |

Los archivos están acompañados de `SHA256SUMS-0.5.3-development.txt`. El ZIP
incluye `DEVELOPMENT-ONLY.txt`. La rama permanece local sin commit ni push; los
activos públicos anteriores no se sustituyeron. El estado de la copia privada
se comprobó y conserva los tres cambios que ya tenía al inicio.
