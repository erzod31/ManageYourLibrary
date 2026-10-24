# Implementación y validación de las mejoras de Manage Your Library

24 de octubre de 2026. Rama local `codex/audit-optimizations`, basada en
`a7304c6dee8474f6e538f775db655eccf6be4800`. Los cambios no forman parte de los
paquetes públicos 0.5.3. El repositorio privado anterior no se modificó.

Se han implementado las correcciones reproducidas de catálogo, concurrencia,
identidad y lectura limitada, junto con mejoras de importación, recuperación e
interfaz. La continuación cierra los bloques locales de aislamiento, copia,
revisión, entidades, cancelación y medición reproducible descritos al final.
**La validación universal no está cerrada**: las comprobaciones nativas de
Mac/Linux, accesibilidad asistida y firma se distinguen expresamente de las
pruebas locales. Una compilación de desarrollo no es una aprobación de publicación.

## Decisión tecnológica

Se mantienen Python 3.12, SQLite y la interfaz Tkinter. La escritura incremental
elimina el principal problema medido sin una reescritura de lenguaje. El prototipo
Qt queda separado del producto y de sus dependencias distribuidas. No se añaden
Rust, C#, RapidFuzz, otro motor OCR ni modelos pesados sin una ventaja comprobada
en una carga representativa.

El prototipo PySide6 6.12.0 utilizó 50.000 filas, 23 widgets y cuatro imágenes
compartidas. En 100 muestras obtuvo p95 de 14,19 ms en búsqueda, 0,69 ms en selección
y 5,40 ms en tema; RSS de 200,04 MiB y separación máxima entre latidos de 31,91 ms.
No incluye persistencia, importación, OCR ni todos los diálogos de la aplicación.
Sus roles accesibles se consultaron mediante Qt, no mediante NVDA o VoiceOver.
Es una razón para seguir evaluándolo, no una comparación de productos equivalentes.
El diseño del prototipo usa el modelo y la vista de listas nativos de Qt.
[QAbstractListModel](https://doc.qt.io/qt-6/qabstractlistmodel.html),
[QListView](https://doc.qt.io/qt-6/qlistview.html).

## Cambios implementados

### Catálogo y recuperación

- SQLite pasa a ser la autoridad de los registros, con revisiones para rechazar
  guardados completos obsoletos. Favoritos y correcciones actualizan una sola fila.
- La sincronización masiva usa una tabla temporal, no miles de parámetros en un
  `NOT IN`. Se verificaron 100.000 registros persistidos.
- La migración conserva el JSON original. Una proyección SQLite anterior con datos
  se respalda antes de activarla. JSON dañado o modificado después de migrar genera
  un error explícito; no se interpreta como una biblioteca vacía.
- Una instancia compatible por perfil, planes con propietario activo y recuperación
  de propietarios muertos. Las modificaciones parciales y fallos siguen registrados.
- Copia de perfil con instantáneas SQLite, manifiesto SHA-256 y restauración de
  comprobación desde la interfaz. Restaurar exige una carpeta nueva o vacía y nunca
  activa automáticamente el resultado. Las carpetas externas de libros no se incluyen.
- Las correcciones humanas se protegen por campo, sin asignar automáticamente 100
  de confianza a datos que la persona no ha confirmado.

Los identificadores sobreviven a la corrección del único archivo de una edición.
La continuación añade IDs de archivo independientes de la ruta e historial para
movimientos comprobados por diario y hash. No equivale a cubrir todas las
combinaciones de ediciones y operaciones manuales ajenas a la aplicación.

### Identificación y procesamiento

- Repetir resultados de una fuente no aumenta la puntuación, tanto en el motor de
  identidad como en el consenso final. El orden de las evidencias no altera los
  casos comprobados. Conflictos de idioma, edición o volumen impiden renombrado
  automático; se normalizan alias habituales de idiomas.
- Se invalida la caché antigua con la política `identity_v12_independent_evidence`.
  Una puntuación nueva inferior también puede reducir la proyección del catálogo.
- PDFium comparte exclusión entre portadas y OCR. Se cierran páginas y bitmaps;
  se limitan píxeles, expansión de miembros ZIP y lecturas de texto antes de cargar
  todo el contenido. Los procesos externos tienen límites de salida y tiempo.
- Cola de análisis acotada y cancelación sin esperar al cierre de procesos en el
  hilo gráfico. Circuito de proveedores con recuperación, caché utilizable durante
  fallos, control de tasa y cancelación heredada.
- Redirecciones de portadas comprobadas antes del contacto y limitadas al proveedor
  permitido. Las miniaturas permanecen en disco; las imágenes visibles necesitan
  memoria temporal. No se cambia la política de OCR local.
- Los planes comprueban tamaño, contenido e identidad estable durante el hash.
  Los casos ambiguos no pasan a renombrado o cuarentena automáticos.

### Importación e interfaz

- Análisis y captura de firmas fuera del hilo gráfico, antes de confirmar cambios.
  El plan persiste sin guardar páginas OCR ni texto completo de los documentos.
- Previsualización paginada de todos los elementos, origen completo, nombre y destino
  propuestos, fuente y motivo. «Catalogar sin mover» conserva originales en su lugar;
  «Organizar» requiere confirmación de movimientos y cuarentena de duplicados exactos.
  El destino mostrado sigue sujeto a la comprobación posterior de duplicados.
- Estados Por leer, Leyendo y Leído, filtro de revisión y filtros guardados. Un
  archivo de vistas dañado no se sobrescribe silenciosamente al guardar otra vista.
- Tablas y portadas muestran páginas de 30 elementos; no se crean 50.000 filas Tk.
  Las órdenes por título y fecha se preparan una vez y se actualizan por registro.
- Acciones y ruta seleccionable en la parte inferior de Detalles, menús oscuros y
  atajos coherentes. Con poco espacio se oculta la portada y se agrupan relaciones;
  «Detalles…» abre los datos completos. Las columnas laterales no tienen scroll.

## Pruebas y rendimiento

La primera iteración ejecutó **452 pruebas, sin fallos y con 2 omitidas** por permisos
de enlaces simbólicos. Incluye fallos de transacción, protección de fuentes,
migración, restauración, conflictos de revisión, planes activos y entradas hostiles
acotadas. Un caso genera 500 variaciones sintéticas de contradicciones; no son
500 pruebas independientes ni una medición de precisión sobre libros reales.

Ruff 0.16.9 pasó las reglas de errores seleccionadas `E9,F63,F7,F82`; esto no es
una auditoría completa de estilo o tipos. `pip check` no detectó incompatibilidades.

Persistencia de la primera iteración en Windows 11, Python 3.12.10, con tres calentamientos y cien
ediciones por tamaño. Son perfiles sintéticos nuevos, sin libros personales.

| Registros | Guardado inicial | Mediana de edición | p95 de edición |
| --- | ---: | ---: | ---: |
| 1.000 | 107,41 ms | 11,23 ms | 12,41 ms |
| 10.000 | 1.236,47 ms | 14,12 ms | 15,65 ms |
| 50.000 | 12.063,77 ms | 17,68 ms | 22,18 ms |
| 100.000 | 28.672,88 ms | 23,04 ms | 32,32 ms |

La referencia anterior de 50.000 filas tardaba 8–11 segundos por favorito y tenía
un fallo de límite SQL. Esa referencia tuvo solo tres muestras; no es un ensayo
estadístico equivalente. El primer guardado/migración sigue siendo costoso y ahora
se ejecuta detrás de la pantalla de carga, no dentro de un evento de interacción.

La búsqueda preparada obtuvo p95 de 13,28 ms a 50.000 filas y 28,58 ms a 100.000,
con cien muestras. No incluye espera de teclado ni pintura. La memoria adicional
del índice preparado a 100.000 fue 166,85 MiB; no es la RAM total del proceso.

La medición final de la ventana y la huella del ejecutable figuran en el
[registro de validación Windows](windows_audit_2026-10-24_checksums.md). Separan
tiempo de callback, actualización completa, latidos, construcción y RSS. El
desplazamiento de una división medido como llamada no certifica todo el arrastre
ni la presentación de cada fotograma.

Los datos completos quedan conservados: [persistencia](validation_data_2026-10-24/persistence.json),
[Tk](validation_data_2026-10-24/tk-ui.json), [catálogo](validation_data_2026-10-24/catalog.json),
[geometría y flujos](validation_data_2026-10-24/layout.json),
[prototipo Qt](validation_data_2026-10-24/qt-prototype.json) e
[inventario Python](validation_data_2026-10-24/python-sbom.json).

La sonda geométrica comprueba 1024×768, 1366×768 y 1920×1080 con cuatro escalas
Tk, 100/125/150/200 %. También prueba comandos de filtros, guardado y recarga de
una vista, y acceso al elemento 1005 de una previsualización. El menú se simula
en esa sonda para evitar el bucle modal nativo de Windows. La revisión visual
real comprobó selección, menú oscuro de lectura y guardado del estado.
Cambiar la escala de Tk no certifica los cuatro escalados del sistema operativo.

## Dependencias y licencia

Se actualizaron Pillow a 13.0.0, pypdf a 6.21.2, pypdfium2 a 5.14.0 y setuptools
a 84.2.1, con versiones y hashes de ruedas Windows fijados. Se instalaron en un
entorno independiente y se repitieron pruebas y OCR sintético.

`pip-audit` 2.10.1 pasó de 101 entradas de avisos, algunas duplicadas, en tres
paquetes anteriores a **cero avisos conocidos para los 12 paquetes Python fijados**.
No demuestra explotación previa ni ausencia universal de vulnerabilidades. El
inventario Python no cubre todas las DLL, Tesseract ni componentes del sistema.
La nueva versión de PDFium exige macOS 13 o posterior; construir y verificar
paquetes nuevos en Mac/Linux sigue pendiente. [Release PDFium](https://github.com/pypdfium2-team/pypdfium2/releases/tag/5.14.0).

Las acciones de CI están fijadas por revisión y usan permisos de lectura;
Dependabot y auditoría de dependencias quedan configurados. No se ha ejecutado
esa nueva configuración en GitHub porque esta rama no se ha subido.

La licencia del código es [MIT](../LICENSE), copyright 2026 erzod31, por elección
expresa del propietario. Los componentes distribuidos conservan sus propias
licencias, recogidas en [los avisos de terceros](../THIRD_PARTY_NOTICES.md).

## Probar sin comprometer el perfil habitual

Para la primera prueba, usa un perfil nuevo y copias de unos pocos libros:

```powershell
python -B main.py --profile "D:\MYL-Prueba"
# En una compilación completa extraída:
.\ManageYourLibrary.exe --profile "D:\MYL-Prueba"
```

El perfil no debe ser la carpeta de libros ni una raíz de disco. Las nuevas
instancias respetan el bloqueo de perfil; versiones antiguas no conocen ese
bloqueo. **No abras una versión anterior sobre un perfil migrado**: su JSON es una
copia anterior, no el catálogo actualizado. Conserva una copia previa para volver
a la versión anterior, o exporta explícitamente el catálogo actual a otro archivo.

Configuración permite copiar el perfil, restaurarlo en otra carpeta y exportar
JSON. Una restauración fallida puede dejar una carpeta parcial que no se activa;
conserva el archivo ZIP y el perfil original para diagnosticarla. Respaldar el
perfil no sustituye respaldar los libros externos.

Las pruebas deben ejecutarse mediante `python -B tools/run_tests.py`. Durante el
trabajo se descubrió una prueba heredada que activaba migración sobre el perfil
local: se detuvo, se conservó una copia privada y se retiró la activación. Ningún
libro se movió o eliminó. La proyección SQLite sí se había resincronizado, por lo
que no se afirma que el perfil quedase idéntico byte a byte. La prueba y el runner
quedaron aislados; ni el respaldo ni los datos personales se incluyen aquí.

## Continuación: cierre de los bloques locales

- **Lectores aislados.** Los puntos de entrada de extracción rápida/completa,
  lectores estructurados y OCR de archivos, y la decodificación de portadas locales
  o descargadas, se ejecutan en procesos desechables. Hay dos plazas de documento
  y dos de portada; presupuestos de 30/50/180 segundos y 512/1024 MiB según tarea.
  Un fallo de lector deja revisión pendiente, no autoriza renombrar. El arranque
  congelado comprueba también este protocolo. Los límites Windows usan un Job
  que incluye descendientes; POSIX usa límites de recursos y grupo de procesos.
  Esto aísla fallos, **no es un sandbox de seguridad ni una restricción de acceso
  al disco del usuario**. [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
  [resource](https://docs.python.org/3/library/resource.html).
- **Copia recuperable.** Nuevo botón «Importar copias», publicación sin sobreescribir,
  verificación de origen y destino, diario, reserva de destino y reanudación sin
  duplicar una copia confirmada. Deshacer traslada solo la copia a cuarentena del
  perfil. Los originales permanecen intactos; los archivos parciales se conservan
  con su registro. Los casos ambiguos no se copian automáticamente.
- **Revisión y reanudación.** Comparación de ocho campos: actual, propuesta,
  resultado protegido, fuente y motivo. Los conflictos con correcciones humanas
  bloquean movimiento/copia. El análisis de cada elemento se guarda y puede
  reanudarse sin repetir los lectores que terminaron. Las firmas y el escaneo son
  cancelables. Una carpeta inaccesible o raíz ausente aborta el guardado parcial.
- **Entidades.** Autores, Series y Etiquetas tienen directorios paginados con
  recuentos y navegación exacta, no búsquedas por subcadena. Son agrupaciones de
  navegación por nombre normalizado, no prueba de identidad bibliográfica. Los
  movimientos verificados por diario y hash conservan ID del archivo y correcciones,
  con historial de ubicaciones. La reutilización de una ruta obtiene otro ID.
  No se fusionan automáticamente identidades ambiguas; el diario conserva las
  sustituciones y cuarentenas, sin afirmar cobertura de toda combinación posible.
- **Interfaz.** Pintura agrupada en tramos de unos 4 ms, reconstrucción de vistas
  grandes en segundo plano, Deshacer fuera del hilo gráfico y cierre que espera
  a los trabajadores sin liberar prematuramente el perfil. Alto contraste añadido.
  Se localizaron pausas del recolector de generación 2; la aplicación independiente
  aparta el catálogo de larga vida de esos recorridos y lo devuelve al recolector
  al cerrar. El conteo de referencias y GC de objetos nuevos siguen activos.
  Las mediciones antes/después y de memoria están en el registro Windows.
  [Semántica de freeze/unfreeze](https://docs.python.org/3.12/library/gc.html#gc.freeze).
- **Evaluación versionada.** `tests/fixtures/identity_corpus_v1.json` contiene casos
  sintéticos originales MIT, separados en ajuste/evaluación. En evaluación:
  12 casos, cinco decisiones automáticas correctas y cero decisiones inseguras;
  cobertura automática 41,67 %. Tres imágenes OCR sintéticas dieron texto exacto,
  con 0 de error de caracteres. Es evaluación de regresión de evidencia y OCR,
  **no precisión de identificación sobre una población de libros reales**. No se
  ajustó el algoritmo a esos resultados ni se movió ningún libro del usuario.
  [Resultados](validation_data_2026-10-24/corpus-completion.json).
- **Distribución.** Los validadores exigen la prueba del lector congelado; el
  instalador y el empaquetador admiten destinos independientes y rechazan
  reemplazar paquetes existentes. La prueba Windows usa un AppId único y otro
  perfil, no la instalación habitual. Resultado y huellas en el
  [registro Windows](windows_audit_2026-10-24_checksums.md).

## Límites pendientes que requieren otra validación o decisión

El listado siguiente conserva el estado al cierre del 24 de octubre. La
[continuación del 25 de octubre](VALIDACION_NATIVA_Y_ACCESIBILIDAD_2026-10-25.md)
registra la autorización de la rama de pruebas, validaciones nativas ejecutadas
y el alcance pendiente de accesibilidad. La
[revisión por DLL](LICENCIAS_OCR_2026-10-25.md) actualiza la procedencia y licencias.

1. Ejecutar los nuevos builds y pruebas de proceso/OCR en hosts reales macOS/Linux.
   Los workflows están preparados; no se han subido ni ejecutado desde esta rama.
2. Accesibilidad completa: alto contraste, geometría y navegación comprobables no
   convierten los Canvas de Tk en controles accesibles nativos. Queda validación
   con NVDA/VoiceOver y DPI real. Resolver todos los roles/nombres del sistema
   puede requerir una capa nativa o migración de interfaz; no se disfraza una
   propiedad Python `accessible_name` de soporte real de lector de pantalla.
3. Qt queda como evaluación opcional: no se incorpora ni se reescribe la app.
   Una migración exigiría paridad de importación, recuperación, accesibilidad y
   empaquetado, y una decisión explícita sobre ese cambio de alcance.
4. La firma Windows y notarización macOS requieren certificados/cuentas del
   propietario. No se han creado credenciales, commits, tags, releases ni subidas.
5. Las pruebas sintéticas no sustituyen un corpus representativo de ediciones,
   idiomas y escaneos reales con derechos de redistribución y etiquetas revisadas.
   Tampoco garantizan latencia máxima en cualquier hardware, biblioteca o lector.
6. La inspección final encontró avisos de dependencias ausentes del paquete.
   Se incorporan las licencias Python disponibles y los textos Apache de OCR,
   pero las DLL del runtime Windows heredado aún requieren procedencia exacta,
   revisión de avisos/obligaciones de redistribución y seguridad. Esto bloquea
   aprobar una nueva publicación; MIT del proyecto no sustituye esas licencias.
   Véase [el inventario y sus límites](../THIRD_PARTY_NOTICES.md).

El número exacto de pruebas del cierre, los resultados instalados y los paquetes
generados constan en el registro Windows; los números de la primera iteración
anteriores se conservan como referencia histórica, no como medición final.

La repetición de cierre tiene 478 pruebas (2 omitidas), 12 escenarios geométricos
y nueve comprobaciones de flujo correctas. Con 100 ediciones por tamaño, la
persistencia a 100.000 registros obtiene mediana 18,58 ms y p95 26,11 ms;
guardado inicial 21,06 s. No se promete ese tiempo en otras máquinas.
[Persistencia del cierre](validation_data_2026-10-24/persistence-completion.json),
[geometría del cierre](validation_data_2026-10-24/layout-completion.json),
[interacción aceptada](validation_data_2026-10-24/tk-ui-accepted.json).

La revisión visual adicional usó 400 registros sintéticos: directorio de autores,
selección con teclado, pertenencia exacta de los libros y cambio de tema desde
esa página. No es una sesión con lector de pantalla ni sobre un perfil personal.
El transporte del lector no depende de `stdin`, que no existe en la compilación
Windows sin consola, y los checkpoints de previsualización vuelven a comprobar
las correcciones humanas realizadas durante una pausa.
