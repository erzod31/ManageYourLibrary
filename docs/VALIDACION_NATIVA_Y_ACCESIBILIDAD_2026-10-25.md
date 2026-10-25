# Validación nativa y accesibilidad — 2026-10-25

Continuación del informe del 24 de octubre. La autorización nueva permite subir
la rama `codex/audit-optimizations` para pruebas, **no publicar una versión**.
No se han creado tags, fusionado `main` ni modificado versiones publicadas.
El repositorio privado y el perfil/biblioteca del usuario quedan fuera del trabajo.

Actualización local posterior: se reparó y reconstruyó el proveedor Windows,
y se incorporó la voz local de la app solicitada por el usuario. Las secciones
históricas conservan sus límites originales; los resultados nuevos figuran en
«Reparación local y control explícito de voz». Esa primera reparación se probó
sobre `7bd30dd` con cambios locales: en aquel punto todavía no había commit ni
EXE nuevo. El cierre posterior registra por separado su revisión y artefactos;
no equivale a publicar una versión.

La [sesión posterior de cierre](windows_completion_2026-10-25_checksums.md)
añade la prueba autorizada con NVDA real, salida SAPI a WAV y las comprobaciones
de construcción/paquete que efectivamente se completen. Sus resultados no se
atribuyen retroactivamente a los artefactos anteriores.

## Evidencia nativa completada

La revisión `0e900c58c7a833c39874768b50ed90109b495d49` pasó los tres trabajos del
[workflow nativo 40138402715](https://github.com/erzod31/ManageYourLibrary/actions/runs/40138402715):

| Host real de CI | Resultado | Límites |
| --- | --- | --- |
| Ubuntu 22.04, x64 | Correcto | No certifica otras distribuciones, Wayland, ARM ni lector Orca. |
| macOS 15, Apple Silicon | Correcto | Firma ad-hoc; sin Developer ID ni notarización. |
| macOS 15, Intel | Correcto | Mismos límites de firma; no certifica macOS anteriores. |

Se construyeron Tcl/Tk 9.1.0 y el puente de CPython desde fuentes fijadas por
SHA-256, ejecutaron las pruebas, comprobaron propiedades/acciones de la API
nativa, empaquetaron OCR y dependencias nativas, probaron ejecutables congelados
con OCR de imagen/PDF, PDFium, lector en proceso aislado y primer uso vacío sin
red. Los archivos empaquetados se extrajeron y volvieron a probar. El trabajo de
publicación quedó **omitido**, no se publicó una release.

El workflow conserva manifiestos, hashes y dependencias exactas por arquitectura.
La repetición posterior añade al artefacto el informe de API de accesibilidad y
el archivo de fuentes GUI fijadas; sus resultados pertenecen a su propio commit
y ejecución de Actions, no se confunden con la ejecución anterior.

La revisión posterior `7bd30dd0ac3f3cf462ae186cd2f5fc3e5212f20b` también
completó los tres destinos en el
[workflow 40172149124](https://github.com/erzod31/ManageYourLibrary/actions/runs/40172149124).
Cada job registra **507 pruebas, una omitida**, OCR de siete formatos, cinco
modelos juntos y TSV correctos. macOS Intel: `121105066961`; macOS ARM64:
`121105067104`; Linux x64: `121105067156`. Las comprobaciones de runtime y primer
uso empaquetado terminaron correctamente. `publish` quedó **skipped**.
Estos resultados no incluyen los cambios locales posteriores de limpieza y foco.

## Problemas encontrados y corregidos

- macOS no admite los mismos límites `RLIMIT_AS`/`RLIMIT_DATA` que Linux en estos
  lectores. Se conserva límite duro de memoria en Linux y se usa vigilancia de
  memoria residente en macOS con `libproc`. Es muestreo cada 25 ms y terminación
  del proceso excedido, **no un límite atómico de asignación ni un sandbox**.
- Se corrigió la carrera entre salida del trabajador y consulta de memoria en
  Darwin. Las rutas temporales macOS se comparan canónicamente (`/private/...`).
- Tk 9.1 requiere HarfBuzz para texto bidireccional en Linux. Se añadieron las
  dependencias de desarrollo y el servicio AT-SPI para la prueba con sesión D-Bus.
- El patrón `libtcl9*.so` también encontraba Tk; ahora se enlazan nombres exactos
  de Tcl y Tk. No se depende del orden del directorio para resolver bibliotecas.
- En macOS, los ZIP de scripts anexados al Mach-O impedían `install_name_tool`.
  La construcción Unix usa `--disable-zipfs` y bibliotecas de scripts ordinarias.
- El congelado Windows recoge explícitamente las DLL y scripts del runtime GUI
  aislado; no busca sus DLL en la instalación Python global. Se conservan avisos
  de Tcl, Tk, libtommath, zlib, utf8proc y SheenBidi según el build.
- La limpieza del probe cancela callbacks sin borrar comandos Tcl propiedad de
  widgets hijos; se evita el doble borrado observado en Linux.

## Accesibilidad implementada y alcance real

Se mantiene Python/Tkinter. No se ha migrado la aplicación a Qt ni reemplazado
el Python del sistema. `ui/accessibility.py` usa los comandos nativos de Tk 9.1:
roles, nombres, ayuda, valores, estados y acciones. Los botones dibujados exponen
su acción protegida por estado deshabilitado. Se nombran buscador, controles de
vista, navegación compacta, tablas, ruta completa y campos del editor.

La API pública Tcl puede ser un no-op si no había lector al arrancar; se emplean
sus comandos nativos sin alterar ajustes de accesibilidad, seguridad o privacidad
del sistema. En Windows y macOS el proveedor usa el campo `description` para la
etiqueta visible al cliente; se mantiene allí el nombre y en `help` la explicación.
En ATK el campo `name` conserva su uso normal. Se prueba esta diferencia, en vez
de validar solo un atributo Python.

Se añaden F6/Mayús+F6 para alternar paneles visibles, Ctrl+F/Ctrl+K para buscar,
Enter/Espacio en botones, foco inicial y Escape en el editor. Los nombres se
actualizan al cambiar el idioma. El alto contraste y los temas existentes se
conservan. La tabla sigue disponible como alternativa a las carátulas visuales.

`tools/verify_accessibility.py` comprueba la API real dentro del proceso: nombres
y roles, acción registrada de navegación, selección, valor de ruta completa,
acción deshabilitada, nueve campos de edición y ausencia de errores. Son 18
comprobaciones comunes y una adicional del campo de etiqueta en Windows/macOS.
La prueba usa solo un perfil y libros sintéticos desechables.

**Esto aún no es certificación de accesibilidad completa.** No se han ejecutado
sesiones de voz con NVDA, VoiceOver u Orca ni una matriz de DPI real. La inspección
externa de Windows mostró controles sin etiqueta antes de corregir el campo
nativo. Después del desbloqueo confirmado por el usuario se reanudó la sesión
visual: el cliente externo devolvió `accessibility: null`, incluso solicitando
solo texto. Por ello no se validan externamente nombres, roles, estados ni
acciones accesibles. El resultado interno Tcl no sustituye esa interoperabilidad.
No se alteraron ajustes de seguridad, privacidad o accesibilidad de Windows.

Tk 8.6 continúa funcionando como alternativa de ejecución, pero se declara sin
backend nativo de accesibilidad. No se presenta como equivalente a Tk 9.1.

## Sesión visual Windows después del desbloqueo

Se ejecutó la aplicación desde fuente en el entorno Tk 9.1 aislado con
`tools/benchmark_ui.py --size 80 --preview`. Base Git: `7bd30dd`, más los cambios
locales de limpieza todavía sin commit. No se ensayó un instalador ni se atribuye
esta sesión al ejecutable congelado de una revisión anterior. El perfil temporal,
las cuatro portadas locales y los 80 registros fueron sintéticos. Sus rutas no
apuntan a libros reales; no se activaron Abrir, Buscar en la web, mover, renombrar,
eliminar ni guardar correcciones de metadatos.

Comprobaciones realmente observadas mediante control de escritorio:

| Comprobación | Resultado observado |
| --- | --- |
| Ctrl+F en Biblioteca | Buscador enfocado, cursor visible. |
| Ctrl+K desde Configuración | Vuelve a Biblioteca y enfoca el buscador. |
| Selección de carátula | Título, autor, etiqueta, estado y ruta aparecen en Detalles. |
| Favorito | Cambia a «Favorite» y aparece confirmación en la barra de estado; solo catálogo sintético. |
| Tabla y flecha abajo | Selección visible pasa al siguiente libro y Detalles coincide. |
| Editor manual | Nueve campos visibles, foco inicial en Título; Tab pasa a Autor. |
| Escape del editor | Cierra sin guardar y el botón Editar recupera contorno de foco visible. |
| Claro y oscuro | Cambio visible y desplegable Ordenar legible en ambos. |
| Cliente accesible externo | Devuelve `null`; no se certifican nombres, roles, estados ni invocación externa. |

La primera pasada detectó que F6 enfocaba la ruta vacía sin selección. Se corrigió
el recorrido para omitir destinos vacíos, ocultos o deshabilitados, incluir el
contenido de páginas no bibliotecarias y comenzar por el último destino válido
al recorrer hacia atrás desde fuera. El resto de controles conserva sus acciones;
no se usa F2 en esta validación porque inicia la revisión operativa de metadatos,
no el editor manual.

La repetición posterior confirmó visualmente que, sin selección, F6 desde el
buscador enfoca Biblioteca en vez de la ruta vacía. Mayús+F6 desde la navegación
Importar enfoca su campo de ruta con cursor visible. Se añadió un único helper
para revelar controles recortados en el canvas de la página actual, utilizado
también por Tab/Mayús+Tab mediante `FocusIn` del toplevel principal. El caso de
viewport desplazado se cubrió con regresiones de geometría y foco, pero no se
completó su confirmación visual en una ventana reducida.

La primera pasada de alto contraste encontró el icono de vista activo blanco
sobre amarillo y la barra de título blanca con texto blanco. Se corrigió el
icono para seguir el color de texto efectivo y la apariencia nativa por ventana
Windows, sin cambiar preferencias del sistema. En la última pasada se observaron
el icono activo negro sobre amarillo y la barra de título oscura legible. El
editor y otros diálogos reciben el ajuste de apariencia al mapearse; esa extensión
se probó con dobles, no se volvió a inspeccionar visualmente cada diálogo.

Ambas pasadas con `--theme contrast --output ...` terminaron con `errors: []` en
el registro de callbacks del preview. Se observaron también capturas incompletas
de contenido al perder el foco, recuperadas en algunas activaciones/acciones;
no se determinó si el origen es la captura, la composición de Windows o el
repintado de Tk. No se declara resuelto ni se considera una prueba de corrupción
del catálogo. Las ventanas QA quedaron cerradas al finalizar.

Validación automatizada final sobre estos cambios locales:

- `tools/run_tests.py`, Python 3.12.10/Tk 9.1.0 aislados: **550 pruebas, sin
  fallos; dos omitidas por permisos de symlinks Windows**, 11,955 s.
- `tools/verify_accessibility.py`: **19/19**, sin errores de callbacks/proveedor
  interno, `frozen: false`; cliente externo y voz siguen sin validarse.
- Ruff sin caché (`E9,F63,F7,F82,F401,F811,F841`): correcto en el repositorio.
- `git diff --check`: correcto. No se construyó un EXE/instalador nuevo ni se
  publicaron estos cambios locales.

Huella SHA-256 de los tres archivos de implementación/fixture ejercitados:

```text
library_app.py        4c1d205e47dfa42cb935de8f39c0449e18bca58d88dde3af2f78ff7f036ef507
ui/workspace.py      217b83f8cc41d9f2cb38b95fb575ad146368f7478ccbf0b9bad84ae1448da270
tools/benchmark_ui.py 5f9b6fb7b99ebf789d7ff6b605bab4eddf5e8fb0a8eaa4dd8b58518db01ff092
```

Las capturas de la ventana principal fueron de 1602 × 1064 píxeles; este dato no
es una medición de DPI. No se cambió la escala del sistema. No se introdujo texto
mediante automatización al no disponer de foco expuesto por el cliente externo.
La comprobación no acredita dictado, voz ni orden de lectura de NVDA.

### Inspección inicial del proveedor Windows

Se revisaron los fuentes fijados de Tk 9.1.0, commit
`3f45110c0a568b70f2ebd5412f215e87d199bc7d`, archivo SHA-256
`23a5509d15f24adc901e10f24e0291108735eba156560812067346f13ebf4a85`.
Los archivos extraídos coinciden con ese archivo de fuentes. En esa primera
inspección no se había modificado el proveedor.

- El proveedor Windows implementa MSAA (`IAccessible`), no un proveedor UIA
  nativo. El probe Tcl no comprueba la publicación mediante `WM_GETOBJECT` ni
  la interoperabilidad entre ese proveedor y el cliente externo.
- En `win/tkWinAccessibility.c`, `TkAccChildCount` (línea 1373) cuenta hijos
  directos, mientras `AssignChildIdsRecursive` (línea 1632) asigna identificadores
  recursivos e incluye el toplevel. Hay una inconsistencia de enumeración que
  podría impedir descubrir controles anidados. No demuestra ausencia de voz:
  un lector orientado a eventos de foco podría acceder a ellos por otra vía.
- En las líneas 1699–1757, `ExecuteOnMainThreadSync` libera el evento tras señalar
  el handle; `RunOnMainThreadSync` vuelve a consultar ese evento y, en timeout,
  lo libera aún encolado y cierra el handle dos veces. Además, Tcl es propietario
  del evento encolado y lo libera tras procesarlo (`generic/tclNotify.c`, líneas
  424–428 y 725–761). Es un riesgo estático de uso tras liberación/doble liberación
  en la ruta interhilo; no se encontró una referencia retenida que lo resuelva.

En la inspección inicial estos riesgos **todavía no se habían reproducido** y
no se presentaron como la causa del árbol externo `null`. El trabajo posterior
descrito a continuación sí reprodujo el fallo de memoria. Sigue siendo necesaria
la interoperabilidad externa: los getters internos no sustituyen esa prueba.

### Reparación local y control explícito de voz

Se añadió el parche mantenido por el proyecto `myl-tk91-win-msaa-1`. No es una
corrección publicada por Tk ni cambia el archivo de fuentes original. El
aplicador exige los hashes completos de los dos archivos originales y conserva
un recibo con hashes de entradas, salidas, helpers y receta; rechaza reanudaciones
con fuentes modificadas. Las fuentes y licencias originales permanecen intactas.
La modificación se aplica únicamente a los fuentes extraídos del entorno de
construcción aislado, no al Python global ni a la instalación habitual.

Cambios ejercitados:

- El evento Tcl y la solicitud interhilo tienen propietarios distintos. La
  solicitud retiene su handle hasta la última referencia; un timeout pendiente
  se cancela sin reutilizar punteros a la pila del cliente.
- Trece métodos COM se ejecutan en el hilo propietario de Tk, preservando el
  estado del intérprete. Las acciones pendientes invalidan widgets destruidos
  y vuelven a comprobar visibilidad y estado antes de invocar.
- Enumeración y recuento comparten recorrido visible. Los identificadores son
  estables y no se reutilizan al destruir/recrear widgets; cada diálogo tiene
  proveedor propio. `IEnumVARIANT` tiene su propio contrato y protección
  concurrente. Se corrigieron el padre, el rol cliente y el reenvío
  `WM_GETOBJECT` desde el wrapper, aunque este último sigue sin validación externa.
- Los metadatos interactivos de Detalles se vuelven a anotar al cambiar, sin
  esperar a otro evento de foco. Los botones Tk invocan el widget, no un callback
  crudo que pudiera saltarse el estado deshabilitado.

Pruebas nativas realizadas en Windows x64:

| Prueba | Resultado y alcance |
| --- | --- |
| Control negativo con el dispatcher original verificado por hash | AddressSanitizer reprodujo un uso tras liberación. |
| Mismo harness con el header reparado | Nueve escenarios, 480 solicitudes paralelas, 483 callbacks; cero asignaciones/handles pendientes contabilizados por el harness. |
| Enumerador COM reparado | Ocho casos de contrato, 400 elementos consumidos concurrentemente; referencia del propietario conservada. |
| Runtime Tk 9.1 reconstruido | Compilación y activación en venv aislado correctas; identidad del parche comprobada. |
| COM real dentro del fixture Tk, desde hilo secundario | 16/16 comprobaciones, sin errores de callbacks o propiedades. |
| API nativa en la app sintética | 19/19 comprobaciones, sin errores; `frozen: false`. |
| Primer uso vacío | 5/5; ahora comprueba además voz apagada, sin hilo/poll de voz y controles explícitos presentes. |

El harness usa el código real del dispatcher/enum y handles/hilos Windows reales,
con una cola Tcl simulada para controlar carreras. **El runtime Tk completo no
se compiló con ASan** y no se declara ausencia global de fugas: LeakSanitizer no
se ejecutó. La reconstrucción final exige el contrato de 16 comprobaciones y
retiene sus resultados y los fuentes de prueba en la procedencia del runtime.
Una repetición intermedia encontró una DLL en uso por el preview; se cerró ese
preview y la reconstrucción siguiente terminó correctamente. No se forzó la
descarga de DLL ni se terminaron procesos de otras aplicaciones.

#### Voz local, no NVDA

El usuario eligió explícitamente voz local limitada a la app. `AppSpeech` no
crea motor, objeto COM ni hilo antes de pulsar **Activar**. La fila persistente
en la zona inferior muestra el estado y los botones **Activar / Desactivar**;
no depende de la página ni del bloqueo de una operación. La preferencia activa
no se guarda: cada apertura empieza apagada. Desactivar descarta el texto
pendiente y purga/cierra únicamente la instancia de voz de la app. Al perder
el foco de la app se pausa y no se acumulan anuncios antiguos; cerrar la app
cierra su sesión. El estado de error/no disponibilidad es visible.

Se leen etiquetas de controles y título/autor seleccionados, no valores escritos,
contraseñas, registros, contenido de libros ni OCR. La cola conserva como máximo
un anuncio de 400 caracteres. Windows usa su SAPI instalado, sin descarga de
lector, dependencia nueva, servicio de voz web ni cambios de inicio del sistema.
Las llamadas son asíncronas, purgan las anteriores y marcan el texto como literal,
no XML ni ruta de archivo, según las
[opciones documentadas de SAPI](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ee125223(v=vs.85)).
Esta primera implementación de voz es **solo Windows**; macOS/Linux conservan
su accesibilidad nativa y muestran la voz local como no disponible. La voz
propia es una ayuda adicional, no un reemplazo ni certificación de un lector
de pantalla completo. La accesibilidad pasiva no se apaga con esos botones.

Las pruebas de ciclo de vida, concurrencia, controles Tk, privacidad de campos
y argumentos/ABI COM emplean motores falsos sin audio. Se ejercitó incluso el
adaptador de vtable ctypes con un objeto COM falso en memoria, no con SAPI real.
Se comprobó visualmente la fila apagada en Biblioteca y Configuración, en
ventana normal (1602 × 1064 de captura) y reducida con geometría Tk `760x560`
(952 × 740 de captura). Ambos previews terminaron con `errors: []`. Esto no
es una prueba de voz real, DPI completo ni instalador. En tamaño mínimo siguen
observándose limitaciones de espacio de la barra de filtros/estado preexistente;
no se declaran resueltas por esta fila nueva.

Se localizó NVDA 2026.2 en la web oficial, se verificó la firma válida de
NV Access y se preparó una copia temporal portátil fuera del repositorio. El
usuario autorizó su ejecución y después pidió detenerla: se cerró mediante
su opción de salida y se confirmó que no quedaban procesos NVDA activos. No se
instaló ni se añadió al inicio. **No se volvió a ejecutar ni se activó audio**
después de esa petición. No se completó una lectura real con NVDA; la captura
externa del cliente de automatización continuó sin árbol accesible. Por tanto
esa interoperabilidad y la salida de voz real siguen pendientes de una sesión
que el usuario active voluntariamente.

Validación final de código (perfiles temporales, OCR controlado, sin audio):

- Python 3.12.10 + Tk 9.1.0 reparado: **594 pruebas, sin fallos, dos omitidas**
  por permisos de symlink Windows, 12,668 s.
- Python 3.12.10 + Tk 8.6.15: **594 pruebas, sin fallos, las mismas dos omitidas**,
  12,088 s. Este resultado no convierte Tk 8.6 en proveedor nativo accesible.
- Se incluyen 34 pruebas silenciosas de sesión, controles y adaptador SAPI.
  La huella de construcción ahora incluye `.c` y `.h`; una regresión comprueba
  que cambiar fuentes/headers nativos invalida esa huella.
- Runtime desde fuente: **5/5**, incluidos OCR de imagen/PDFium y lectores
  aislados. No es un ejecutable congelado ni un instalador nuevos.
- Ruff sin caché (`E9,F63,F7,F82,F401,F811,F841`) y `git diff --check`: correctos.
- Confirmación final de procesos: **cero NVDA activos**; previews QA cerrados.
- No se creó commit, tag, push ni release durante este trabajo local.

Hashes SHA-256 de implementación ejercitada (no corresponden al EXE publicado):

```text
core/app_speech.py         84e87a87ff4d30ca5b7baf2e8319fd8b894d5c8ea76090f45bdb99f600d13a83
core/sapi_speech.py        dc91e49b8f7749b66cf12b467371170238c3baa243a09aa1895307d4e2db8077
ui/app_speech.py           922ade099d5fdd53b38627daae0b449f85e5b5d3f6f9fbd87258365300006bc9
ui/workspace.py            a775451129026c871e84236e2413c69e67936de28f51836c58942a20ad81a542
tools/build_accessible_tk.py c60cdd793bff8a9619f7d821d6f5ad683b4bbebf7df31338530a62fe3181267a
tools/tk_windows_patch.py  6938fa246390b62d690bff675aedd24703e06729aa36ade975fcc37bc84c43dd
```

## Cómo reproducir sin tocar la instalación habitual

En CI, `.github/workflows/native-release.yml` resuelve ruedas nativas, construye
el runtime GUI fijado, ejecuta el probe y usa los scripts de plataforma existentes.
Los pushes de la rama de pruebas no pueden activar el trabajo de publicación.
Las ejecuciones de push obsoletas pueden cancelarse al llegar otra revisión.

En Windows se requiere Python 3.12 y un compilador MSVC x64 de Build Tools:

```powershell
py -3.12 -m venv C:/myl-native-build/venv
C:/myl-native-build/venv/Scripts/python -m pip install --require-hashes -r requirements.lock
C:/myl-native-build/venv/Scripts/python -B tools/build_accessible_tk.py --output C:/myl-native-build/gui
C:/myl-native-build/venv/Scripts/python -B tools/verify_accessibility.py --output dist/accessibility-self-test.json
$env:MANAGE_YOUR_LIBRARY_PYTHON = "C:/myl-native-build/venv/Scripts/python.exe"
$env:MANAGE_YOUR_LIBRARY_DIST_DIR = "$PWD/dist/windows-tk91"
./platforms/windows/BUILD_WINDOWS.bat
```

Los destinos deben ser nuevos. La activación `.pth` se escribe únicamente en ese
entorno virtual. Los libros, el catálogo y la instalación habitual no son entradas
de estas pruebas. No se distribuyen los binarios generados dentro del historial Git.
La ruta neutra evita incrustar el perfil personal en los fallback de Tcl y los
literales del compilador. La construcción Windows y el empaquetador rechazan
rutas de perfil encontradas en binarios o scripts del runtime; no se parchean
los binarios después de compilar para esconderlas.

## Licencias y publicación

La [revisión individual del OCR Windows](LICENCIAS_OCR_2026-10-25.md) cubre los 57
binarios antiguos y conserva su redistribución pendiente como evidencia histórica.
El [reemplazo OCR controlado](RESOLUCION_GPL_LGPL_OCR_2026-10-25.md) elimina
JBIG-KIT y las dependencias GPL/LGPL de ese payload nuevo; no regulariza paquetes
anteriores ni autoriza automáticamente todas las bibliotecas de la aplicación.
Los componentes macOS/Linux tienen sus propios manifiestos.
Un resultado de compilación, OCR o accesibilidad correcto no sustituye las
obligaciones de licencias, la firma de distribución ni una auditoría de seguridad.

El siguiente cierre requiere interoperabilidad con lectores reales, completar
la revisión de redistribución de la aplicación completa y revisar seguridad nativa.
La puerta de publicación exige esa revisión global aprobada en los tres destinos.
Nada de lo anterior autoriza
publicar una versión nueva sin la decisión correspondiente del propietario.
