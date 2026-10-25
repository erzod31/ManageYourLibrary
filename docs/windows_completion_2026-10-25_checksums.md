# Cierre de comprobaciones Windows — 2026-10-25

Evidencia de desarrollo, no una versión pública nueva ni certificación de
accesibilidad completa. Las publicaciones existentes y el repositorio privado
se conservan. El usuario autorizó una prueba breve de voz local y NVDA portátil;
no autorizó instalar el lector ni añadirlo al inicio.

Este informe es el estado de cierre. Las menciones a «lector real pendiente»,
«sin commit» o «sin EXE nuevo» del informe ampliado describen sus fases anteriores,
no los resultados posteriores registrados aquí. La autorización adicional del
usuario permitió instalar y desinstalar **una copia QA de la app**, no NVDA ni
la instalación habitual de Manage Your Library.

## Lector real y voz local

Se probó la app desde fuente con Tcl/Tk 9.1.0 y el parche
`myl-tk91-win-msaa-1`, catálogo temporal de 80 registros y portadas sintéticas.
La ventana se lanzó antes de los ajustes posteriores de barra compacta, que
tienen su comprobación separada. No se abrió, movió, renombró ni borró ningún
libro real. El editor se cerró con Escape sin guardar.

NVDA 2026.2: ejecutable de NV Access con firma Authenticode válida. Se usó
una copia temporal fuera del repositorio. El menú flotante no era seleccionable
por el controlador de escritorio; se reanudó con un perfil QA independiente y
su visualizador de voz habilitado desde ese perfil. El lector se comunicó con
la app mediante el proveedor real, no mediante atributos Python simulados.

| Acción observada | Texto/semántica mostrada por el visualizador de NVDA |
| --- | --- |
| Foco en Desactivar estando apagado | Botón identificado y «no disponible». |
| Ctrl+F/Ctrl+K | Etiqueta del buscador y rol de edición. |
| F6 y Tab en navegación | Biblioteca y Autores identificados como botones. |
| Enter en Autores | Se abre la vista de autores. |
| Selección de autor y flecha abajo | Nombre de tabla, autor y cantidad; actualiza la fila anunciada. |
| Selección de libro y flecha abajo | Título, autor, formato, tamaño y ruta completa del fixture; cambia el anuncio con la fila. |
| Editor manual | Título y Autor como campos de edición con sus valores sintéticos. |
| Escape | Cierra el editor sin guardar y devuelve el foco. |

Los ejemplos de rutas temporales no se copian al informe para no publicar el
nombre del perfil local. El aviso «Recopilación de Datos de uso de NVDA» no se
respondió automáticamente ni se modificaron sus ajustes de privacidad. Se pudo
probar la app sin decidir ese aviso; al terminar se cerró NVDA por su opción
documentada `-q`. Comprobación posterior: **cero procesos NVDA activos**.
No se guardaron configuraciones en un perfil habitual del lector.

La voz propia se activó desde su botón, se enfocó el buscador y se desactivó
desde el botón visible. El estado volvió a apagado. No se mantuvo funcionando
simultáneamente con NVDA. Se inició una prueba audible autorizada, pero no se
presenta como evaluación humana de inteligibilidad o calidad de pronunciación.

Además, `--local-voice-self-test` ejercita el motor SAPI real con la salida
redirigida y verificada a un WAV temporal **antes** de llamar a Speak. No
reproduce audio ni modifica el dispositivo predeterminado. La primera pasada
desde fuente pasó 14/14: inicio sin motor, activación explícita, PCM real,
pausa/purga, rechazo en segundo plano, desactivación, reinicio explícito y cierre.
Captura: 144.484 frames, 22.050 Hz, mono de 16 bits; muestras no nulas.
La duración del audio renderizado no es tiempo de bloqueo de la interfaz.

## Correcciones y puertas adicionales

- La barra estrecha usa un selector de formatos y dos filas, conservando
  orden, vistas y la acción Importar. Cancelar conserva espacio propio.
- Ctrl+Mayús+M detiene solo la voz de la app, incluso desde un diálogo.
- La prueba de API incluye geometría mínima y controles de voz visibles en
  todas las páginas. Desde fuente: 22/22 comprobaciones correctas.
- El build Windows exige el runtime aislado reparado y ejecuta diagnósticos
  congelados de API, proveedor COM y SAPI a WAV, además de runtime/primer uso.
- El empaquetador exige informes completos, de la misma versión y realmente
  congelados; una bandera booleana o un informe parcial no bastan.
- Las fuentes C y headers forman parte de la huella de construcción.
- Se encontraron rutas internas de compilación con el perfil de Windows en
  Tcl y `_tkinter`. Se reconstruyeron desde un entorno y fuentes en una ruta
  neutra, sin parchear bytes de los binarios. La verificación posterior pasó
  en 175 archivos del runtime y dos del puente. El constructor rechaza rutas
  de trabajo de perfil; el empaquetador vuelve a comprobar todo el payload.
  Es una comprobación acotada de rutas Windows en formatos nativos/texto,
  no una certificación general de ausencia de secretos.
- Repetición desde ese entorno neutro: 615 pruebas en 12,881 s, dos omitidas
  por permisos de enlaces simbólicos de Windows; API/disposición 22/22 y
  proveedor COM 16/16. Una regresión adicional del empaquetador se añadió
  después y se contará en la ejecución de construcción, sin alterar ese dato.
- Revisión visual de la ventana de 760×560 en claro y oscuro: buscador,
  selector de formatos, orden, vistas, Importar, voz y Cancelar conservan su
  espacio. La acción Añadir aparece deshabilitada en el fixture sin biblioteca
  configurada. La ventana se cerró sin errores de callback. No es una matriz
  completa de DPI, fuentes ni tamaños de pantalla.

## Estado de construcción

Primera construcción sobre `aa04989`: EXE y los cinco diagnósticos congelados
correctos (runtime 5, primer uso 5, API 22, COM 16, SAPI 14). La comprobación
completa posterior rechazó cinco archivos generados de procedencia OCR por
rutas locales; **ese paquete no se entrega**. La normalización anterior no
cubría todas las combinaciones de barras y mayúsculas de CMake. Se añadió la
regresión correspondiente y una puerta de privacidad al propio build antes de
generar el manifiesto. No se modificaron archivos originales ni avisos de
licencia: solo la generación de metadatos de construcción.

La validación remota Windows encontró que el botón de prueba de identidad,
añadido como hermano mediante `pack`, podía quedar sin espacio en pantallas
pequeñas. Reproducción local en 760×560: no mapeado, 1×1; con superposición
controlada dentro del fixture: mapeado, 240×36. Se mantiene la exigencia de dos
identidades positivas crecientes, sin omitir el caso; el informe registra
ambos IDs y su visibilidad. La prueba corregida pasó localmente 16/16 (94→95).
Esto corrige el fixture, no cambia el proveedor nativo. El resultado remoto
debe repetirse y registrarse en su ejecución propia.

La repetición remota sobre `9f32b99` confirmó 16/16, con identidades 83→84.
Linux y macOS ARM64/Intel también completaron su construcción, diagnóstico y
reextracción en esa revisión, con publicación omitida. El job Windows avanzó
hasta OCR y detectó otro fallo: `libpng` inserta flags en un script CMake y la
barra de una ruta `D:\a` se interpretaba como escape. Se usan rutas de mapeo
con `/`; se comprobó con MSVC real que `__FILE__` conserva el prefijo neutro
`/usr/src/myl-ocr`. Se añadió su regresión sin cambiar los codecs ni licencias.

## Construcción final comprobada

Código: [`e510e59b4753d97c298c5bb407a371345e3a640a`](https://github.com/erzod31/ManageYourLibrary/commit/e510e59b4753d97c298c5bb407a371345e3a640a),
árbol limpio al construir. Huella de 244 entradas:
`8B3D46948F94E99D32880450238048396A95B266054E22FA60DF36A104400871`.
Los cambios posteriores de este informe derivado no son entradas de compilación.
Autor y committer: `erzod31`, dirección privada correcta con el separador `+`.

Python 3.12.10 x64; Tcl/Tk 9.1.0 con el parche fijado. Dependencias bloqueadas:
pypdf 6.21.2, pypdfium2 5.14.0, Pillow 13.0.0, ftfy 6.3.1 y PyInstaller 6.21.0.
Se usaron los scripts de plataforma existentes, el runtime GUI neutro y OCR
controlado reconstruido con los flags CMake corregidos. No se reutilizaron las
DLL antiguas del OCR.

- Build local: **622 pruebas, 13,864 s, dos omitidas** por permisos Windows de
  symlinks. Compatibilidad Tk 8.6.15: **622 pruebas, 13,479 s, dos omitidas**;
  esto no hace accesible su proveedor antiguo.
- Puerta de catálogos de 1.000, 10.000 y 50.000 registros: correcta.
- Corpus de evaluación: 12 casos sintéticos, cinco decisiones automáticas y
  cero decisiones inseguras; tres fixtures OCR exactos. No es una estimación
  de precisión sobre bibliotecas reales ni implicó operaciones con libros.
- OCR nuevo: 32 archivos de inventario y seis modelos verificados; siete
  formatos con originales intactos, carga conjunta de cinco idiomas y TSV.
- Ruff sin caché (`E9,F63,F7,F82,F401,F811,F841`) y controles Git de whitespace:
  correctos.

Los diagnósticos se repitieron con el EXE construido, el ZIP **extraído** y la
copia instalada después de actualizar su payload QA:

| Diagnóstico congelado | Build | ZIP extraído | Instalado QA final |
| --- | --- | --- | --- |
| Runtime Tk/OCR/PDFium/lector aislado | 5/5 | 5/5 | 5/5 |
| Primer uso vacío y sin red automática | 5/5 | 5/5 | 5/5 |
| API de accesibilidad y disposición | 22/22 | 22/22 | 22/22 |
| Contrato COM y llamadas desde trabajadores | 16/16 | 16/16 | 16/16 |
| Motor real de voz, solo a WAV temporal | 14/14 | 14/14 | 14/14 |

CRC del ZIP correcto; sus **1.181 archivos** coinciden por SHA-256 con el
payload original. Los diagnósticos no modificaron esos archivos. El control de
rutas Windows pasó sobre 261 archivos nativos/textuales, incluido el manifiesto.
Los estados personales, libros y cachés siguen rechazados por el empaquetador.

## Instalación, conservación y retirada QA

Se compiló una variante desde el mismo `.iss`, con AppId
`ManageYourLibrary-QA-A11y-20261025`, destino neutro y sin sección de accesos
directos. Instalación silenciosa sin reinicios ni cierre de otras aplicaciones;
la acción postinstalación no se ejecuta en modo silencioso. No se usó el AppId
de producción. Sus registros de instalación se compararon antes/después: sin
cambios.

Se abrió realmente la app instalada con `--profile` separado: biblioteca vacía,
sin carpeta preseleccionada, voz apagada, botones visibles en Biblioteca y
Configuración, cambio de tema y Ctrl+K al buscador. Esa inspección se hizo
sobre `9f32b99`; después se reinstaló con el payload de `e510e59`, misma versión
0.5.3, y se repitieron los cinco diagnósticos congelados de la tabla.

Los diez archivos del perfil QA —incluidas configuración y bases de catálogo y
planes, más marcadores sintéticos de historial/cuarentena— y el original
sintético externo conservaron sus hashes en reinstalación y desinstalación.
La comprobación inicial de retirada se adelantó a la autolimpieza asíncrona del
desinstalador; se revisó su log y se comprobó el estado final, sin borrar a mano.
Resultado: carpeta instalada y registro QA ausentes, perfil y original intactos.
La copia QA puede reinstalarse desde su instalador conservado. Esto no valida
todas las migraciones de perfiles reales, downgrades o versiones antiguas.

Al finalizar no quedaron ventanas QA ni procesos NVDA activos. No se instaló
el lector ni se modificó el inicio de Windows.

## Rendimiento de interfaz, alcance acotado

Benchmark con 4.158 registros sintéticos, pool de 30 carátulas y cinco
repeticiones: sin errores, sin callbacks medidos de más de 50 ms. Medianas:
división 0,02 ms, recolocación de carátulas 0,21 ms, selección 6,10 ms,
cambio de tema 30,36 ms. Favorito completo, 126,49 ms de mediana.
RSS final 101,95 MiB; pico 104,57 MiB. No se observó pausa GC superior a 5 ms.

Son tiempos de callbacks instrumentados, **no** latencia de entrada a píxel ni
garantía de 60 FPS. El mayor intervalo de heartbeat fue 77,57 ms en interacción
y 399,45 ms al arrancar; construcción de la UI, 647,92 ms. Se conservan esos
límites en lugar de declarar la interfaz universalmente libre de pausas.

## Validaciones remotas del código final

- [Windows, ejecución 40186318597](https://github.com/erzod31/ManageYourLibrary/actions/runs/40186318597):
  correcta. Dos pasadas de 622 pruebas, **sin omisiones** (33,373 s y 42,743 s),
  compilación del GUI reparado, OCR, corpus y build congelado con sus puertas.
- [Linux/macOS, ejecución 40186318615](https://github.com/erzod31/ManageYourLibrary/actions/runs/40186318615):
  Ubuntu 22.04 x64, macOS 15 ARM64 y macOS 15 Intel correctos; 622 pruebas por
  destino, una omitida. Incluye API nativa, OCR, empaquetado y reextracción con
  nuevos diagnósticos. `publish`: **skipped**.
- [Fuente multiplataforma, ejecución 40186318637](https://github.com/erzod31/ManageYourLibrary/actions/runs/40186318637):
  correcta en Linux y macOS.

Son resultados de `e510e59`, no de commits futuros ni de versiones publicadas
antes. El push quedó limitado a `codex/audit-optimizations`; no se fusionó `main`,
creó tag ni publicó una release. Los cambios del repositorio privado permanecen
fuera de este trabajo.

## Artefactos locales de desarrollo

Se entregan el ZIP completo y el instalador con etiqueta `development`;
el EXE no funciona como archivo independiente de su carpeta `_internal`.
Los SHA-256 se volvieron a calcular y contrastar con `SHA256SUMS`:

| Archivo | Bytes | SHA-256 |
| --- | ---: | --- |
| `ManageYourLibrary.exe` | 5.335.178 | `47D05E0EEC163F801BFBE83D58A17E11F0709909109DDF529283A9C8CD508F50` |
| `ManageYourLibrary-0.5.3-development-Windows-x64-portable.zip` | 63.700.856 | `9E16F8278515E896763E819969D33FE0B8824965E38A2901B102028FFE2C864D` |
| `ManageYourLibrary-0.5.3-development-Setup-x64.exe` | 53.373.613 | `F405E8AFC8580D8A1070682B66263E75F63FD25CA402C6B44612DCA323F9ABB6` |
| `build-manifest-0.5.3-development.json` | — | `22B4EBCD486566A8C3439B493A76CEACA0BE377F9F77BBB334175145BF715AE2` |

La validación QA usa una variante de instalador con identidad aislada; no
certifica los accesos directos o el registro de producción del instalador normal.
El manifiesto original conserva `manual_installed_ui: not_run`: no se ha
convertido una inspección limitada en aprobación de toda la matriz manual.
No hay firma de código ni notarización nueva. macOS conserva únicamente firma
ad-hoc de CI.

## Límites y publicación

Las comprobaciones pendientes de voz local Windows y lector real descritas en
la primera fase se ejercitaron con la autorización recibida. Eso no certifica
accesibilidad completa, todos los lectores, braille, DPI o inteligibilidad humana.
VoiceOver/Orca y la matriz amplia de instalación/migración siguen fuera de la
evidencia disponible.

El reemplazo OCR nuevo no distribuye JBIG-KIT ni las DLL OCR GPL/LGPL antiguas.
No regulariza las releases históricas. La **revisión global de redistribución**
de toda la app continúa `not_complete` y no se levantó artificialmente para
crear paquetes públicos. Estos artefactos son de prueba, no una release aprobada.

Referencias primarias: [guía de NVDA](https://api.nvaccess.org/documentation/userGuide.html#SpeechViewer),
[salida SAPI a un stream](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ms723597(v=vs.85)),
[parámetros del instalador](https://jrsoftware.org/ishelp/topic_setupcmdline.htm),
[parámetros de desinstalación](https://jrsoftware.org/ishelp/topic_uninstcmdline.htm).

## Continuación: procedencia y accesibilidad externa

La auditoría posterior encontró dos defectos no detectados por las pruebas
anteriores: 44 UCRT/API-set de una aplicación ajena recogidos por el PATH de
Windows, y una puerta Unix que aceptaba un subconjunto de comprobaciones de
accesibilidad sin ligarlo al ejecutable. Los paquetes anteriores se conservan
como evidencia de desarrollo; sus resultados no aprueban estos cambios nuevos.

La corrección selecciona únicamente entradas nativas de Python, ruedas,
runtime GUI aislado, OCR controlado y Microsoft REDIST identificado. Windows
10+ proporciona UCRT/API sets; las copias app-local se excluyen antes de COLLECT.
Se comprueban hashes de todos los PE seleccionados y del CRT Microsoft firmado,
con versión suficiente para el toolset de Tk. El inventario distingue 23 PE
del Python base de los dos CRT seleccionados por separado; los 25 originales
del Python base se contrastaron con su ZIP oficial, sin confundir ambos grupos.

Se añaden avisos Python, AVIF/AOM/dav1d/0BSD y reconocimientos FreeType/IJG,
sin cambiar los textos upstream ni dar por revisado todo el producto. Unix
incluye además los avisos Tcl/Tk que faltaban. El módulo interactivo readline,
innecesario en esta GUI, queda excluido; las bibliotecas Linux necesarias no se
eliminan para ocultar obligaciones. Un colector en el host original relaciona
los binarios con dpkg y exige fuentes de la versión exacta desde índices Ubuntu
autenticados, conservando copyright, fuentes e índices. La entrega separada de
fuentes no supone por sí misma aprobación legal ni de reemplazabilidad LGPL.

La nueva puerta de API exige el conjunto exacto, versión, plataforma y
procedencia de fuente o SHA del ejecutable, y repite API en el archivo extraído.
Se prepara además Orca real únicamente en CI Linux/Xvfb/D-Bus temporal, sin
salida de voz/braille, sin dispositivos de audio y con preferencias desechables.
No se instala ni activa ningún lector en Windows; VoiceOver no queda probado
por ese ensayo Linux. Resultados de construcción/CI se anotarán después de
ejecutar estas versiones, no a partir de las pruebas internas del controlador.

Verificación previa al commit de este bloque: 711 pruebas, 13,327 s, dos
omitidas por permisos de symlinks de Windows; Ruff y whitespace correctos.
La primera construcción de diagnóstico encontró un `WORKPATH` no expuesto en
el namespace de PyInstaller; se corrigió usando su `CONF['workpath']` real.
No se presenta aquella construcción interrumpida como un EXE validado.
