# Investigación integral de Manage Your Library

Fecha: 24 de octubre de 2026. Versión de referencia: 0.5.3.
Revisión examinada: `a7304c6dee8474f6e538f775db655eccf6be4800`.

## 1. Dictamen

El concepto está bien encaminado: una biblioteca personal local, agradable de
usar y capaz de organizar libros sin destruir originales ni confundir ediciones.
La siguiente etapa debe convertir esa promesa en una experiencia predecible:
acciones rápidas, decisiones bibliográficas explicables y recuperación fiable.

**No conviene reescribir toda la aplicación en otro lenguaje.** Los problemas
medidos más importantes son escrituras completas del catálogo, límites de una
consulta SQL, concurrencia incompatible con PDFium y actualizaciones excesivas de
la interfaz. Cambiar Python por Rust o C# sin cambiar esas decisiones conservaría
buena parte del problema y añadiría riesgo de migración.

La dirección recomendada es:

1. Corregir los fallos de integridad, concurrencia y persistencia reproducidos.
2. Mantener Python y consolidar SQLite como autoridad del catálogo mediante una
   migración comprobable, no una sustitución inmediata del perfil existente.
3. Separar interfaz, servicios, repositorios y trabajadores de documentos.
4. Mejorar la interfaz actual y medir un prototipo limitado de PySide6/Qt antes de
   decidir una migración gráfica.
5. Ampliar funciones de lectura y organización únicamente después de estabilizar
   las operaciones esenciales.

Este informe contiene investigación y propuestas. No representa correcciones ya
implementadas, una nueva versión publicada ni una certificación de seguridad.

## 2. Alcance y evidencia

La referencia es el repositorio público actual de
[erzod31/ManageYourLibrary](https://github.com/erzod31/ManageYourLibrary), cuyo
`main` remoto coincidía con la revisión indicada al comprobarlo. La copia privada
anterior, versión 0.5.2, contiene cambios locales que se conservaron; no se mezclan
sus resultados con los de este informe.

Se revisaron arquitectura, catálogo, persistencia, transacciones, planes,
identificación bibliográfica, duplicados, extracción, OCR, portadas, proveedores
web, interfaz, pruebas y distribución. Se ejecutaron la suite completa, mediciones
con catálogos sintéticos y experimentos aislados de fallos. La ventana real de Tk
se inspeccionó con datos ficticios en temas claro y oscuro, incluyendo biblioteca,
detalles, importación y revisión.

Entorno de estas mediciones:

- Windows 11 x64; Python 3.12.10; Tk 8.6; SQLite 3.49.1.
- Pillow 12.2.0; pypdf 6.13.2; pypdfium2 5.9.0; ftfy 6.3.1.
- Suite actual: **410 pruebas, sin fallos, con 2 omitidas**.
- Datos sintéticos en perfiles temporales; ningún libro o catálogo personal se
  utilizó para las pruebas de carga o de fallo.

Las cifras corresponden a una máquina y a escenarios controlados. No se midió
todavía el rendimiento de Qt, Tauri, Avalonia o Rust. Tampoco se validaron durante
esta auditoría instalaciones, actualizaciones o desinstalaciones reales en Mac,
Linux o Windows, ni se realizó una auditoría exhaustiva de vulnerabilidades de
dependencias. Los informes históricos de paquetes no sustituyen esas pruebas.

### Lo que merece conservarse

- Transacciones de archivos, comprobación de identidad, cuarentena y registros
  de recuperación ya tienen implementación y pruebas.
- La separación conceptual entre obra, edición y archivo existe en el catálogo.
- Hay escrituras JSON atómicas, cachés limitadas, modo sin conexión y OCR local.
- La cuadrícula reutiliza un conjunto de 30 tarjetas; no crea una por libro.
- Existen herramientas de rendimiento, primer uso y validación de paquetes.
- El estilo editorial y las acciones de favorito, etiquetas y metadatos ofrecen
  una base aprovechable; no hace falta rediseñar la identidad visual desde cero.

Estas bases reducen el coste de evolucionar incrementalmente, pero no eliminan
los defectos concretos descritos a continuación.

## 3. Rendimiento medido

### Catálogo preparado y persistencia

| Operación | 1.000 libros | 10.000 libros | 50.000 libros |
| --- | ---: | ---: | ---: |
| Preparar el modelo de consulta | 38,8 ms | 371,1 ms | 2.319,1 ms |
| Buscar en el modelo preparado, p95 | 0,10 ms | 1,23 ms | 11,10 ms |
| Filtrar formato, p95 | 0,08 ms | 0,67 ms | 9,17 ms |
| Memoria máxima adicional de preparar otra vista | 1,56 MiB | 15,36 MiB | 77,04 MiB |
| Sincronizar todo el catálogo con SQLite | 84,2 ms | 1.170,6 ms | 7.843,8 ms y error |
| Persistir un cambio de favorito, tres muestras | 93,7–96,1 ms | 1.039,5–1.070,5 ms | 8.324,3–10.931,7 ms |

Las búsquedas usaron siete repeticiones por tamaño: ese p95 es una estimación
exploratoria, no una distribución estadística robusta. La memoria es el pico
registrado con `tracemalloc` para una vista adicional, **no la memoria total del
proceso**. El tiempo de favorito incluye la función de corrección y guardado, no
el repintado posterior de toda la interfaz.

Con 50.000 filas se obtuvo `OperationalError: too many SQL variables`. La
transacción SQLite se revirtió y la base nueva quedó con cero archivos, mientras
el JSON se guardó. La capa superior ocultó el error y devolvió control como si la
operación hubiera finalizado normalmente. No se perdieron libros en esta prueba:
el defecto demostrado es la divergencia entre el índice JSON y su proyección SQL.

**Conclusión:** buscar es rápido una vez preparada la vista; reconstruir y guardar
todo el catálogo para modificar un solo elemento es el cuello de botella más
evidente. El control de rendimiento actual puede aprobar aunque este problema
siga existiendo, porque comprueba filtros y búsquedas, no persistencia completa.

### Interfaz Tk real

| Medición | 10.000 libros | 50.000 libros |
| --- | ---: | ---: |
| Refrescar portadas, mediana / máximo | 13,85 / 24,14 ms | 42,39 / 54,65 ms |
| Cambiar tema, mediana / máximo | 47,03 / 78,82 ms | 69,18 / 80,42 ms |
| Seleccionar libro, mediana / máximo | 3,90 / 15,74 ms | 11,57 / 15,79 ms |
| Mayor intervalo del latido de eventos durante interacciones | 88,85 ms | 120,76 ms |
| Tarjetas de portada reutilizadas | 30 | 30 |
| Filas que termina cargando la tabla | 10.000 | 50.000 |
| Errores de callbacks registrados | 0 | 0 |

Las mediciones de callbacks no equivalen al tiempo hasta que el usuario ve el
último píxel. Por ejemplo, el benchmark de división de paneles mide la llamada a
`sash_place`, no una secuencia completa de arrastre y composición. La inserción
por lotes de la tabla evita parte del bloqueo, pero no es virtualización: termina
materializando todas las filas.

La recomendación es medir desde entrada hasta presentación, incluyendo selección,
favoritos, arrastre continuo, cambio de tamaño, portadas frías y tareas de fondo.
Ni un callback muy corto ni un test sin excepciones demuestran fluidez completa.

## 4. Fallos y riesgos prioritarios

P1 significa corrección prioritaria antes de ampliar automatismos o anunciar
soporte fiable para bibliotecas grandes. P2 significa siguiente bloque de calidad.
No se asigna P0: no se reprodujo una pérdida irreversible de libros.

### F1 — P1 — Escrituras completas y error SQL oculto

Ubicaciones: `library_core.py:1670`, `library_core.py:1697`,
`core/catalog_store.py:157`, `core/catalog_store.py:234`,
`ui/workspace.py:2084`.

Marcar favorito copia y recorre el índice, vuelve a escribir su JSON y sincroniza
las tres tablas del catálogo. El controlador gráfico realiza esa llamada de
forma síncrona y después refresca la biblioteca. Además, la sincronización crea
un parámetro SQL por ruta en una sola cláusula `NOT IN`.

El límite del entorno probado fue de 32.766 parámetros, coherente con el límite
predeterminado documentado para versiones modernas de SQLite. No es un límite de
capacidad de SQLite para almacenar libros; es un defecto de construcción de esa
consulta. El valor puede variar entre compilaciones. [Límites de SQLite](https://www.sqlite.org/limits.html).

Corrección recomendada:

- Sustituir el `NOT IN` masivo por una tabla temporal de rutas o una generación de
  escaneo. Marcar ausentes únicamente tras completar un escaneo válido y dentro
  de su biblioteca; cancelar un escaneo no debe convertir archivos en ausentes.
- Hacer visibles y recuperables los fallos de sincronización; no mantener un
  `except Exception: pass` en esta frontera.
- Sacar el guardado pesado del hilo de interfaz, con una cola de escritura
  serializada, hasta completar la migración a actualizaciones por registro.
- Evitar reconstruir toda la vista al cambiar un favorito, etiqueta o estado.

Aceptación: sincronización correcta a 50.000 y 100.000 filas; un fallo SQL no se
presenta como éxito; favoritos y etiquetas no bloquean la entrada de usuario.

### F2 — P1 — PDFium puede recibir llamadas simultáneas incompatibles

Ubicaciones: `ui/workspace.py:378`, `core/cover_service.py:233`,
`ocr_engine.py:363`.

Las portadas usan un ejecutor de cuatro hilos. Tanto portadas como OCR acceden a
PDFium sin una exclusión mutua compartida. Un sustituto controlado de PDFium
registró dos entradas simultáneas al constructor de documento. No se provocó un
fallo nativo real: la prueba demuestra ausencia de serialización.

PDFium no permite llamadas simultáneas desde distintos hilos, ni siquiera sobre
documentos diferentes. Su documentación recomienda exclusión mutua o procesos
separados. [Restricciones de PDFium](https://pypdfium2-team.github.io/pypdfium2/python_api.html#incompatibility-with-threading).

Corrección inmediata: una exclusión mutua compartida por **todos** los accesos a
PDFium, incluidos apertura, renderizado y cierre. Evolución: trabajadores por
proceso, con tiempo máximo, límites de recursos y resultados desacoplados de Tk.
Añadir más hilos no es una solución segura.

Aceptación: prueba que verifique ausencia de solapamiento nativo; estrés conjunto
de portadas y OCR; documento malformado no derriba la ventana principal.

### F3 — P1 — Repetir una evidencia aumenta indebidamente la confianza

Ubicaciones: `book_identity_scorer.py:64`, `book_identity_scorer.py:134`,
`bibliographic_validator.py:40`.

Prueba con el mismo candidato de Open Library, sin añadir ninguna fuente nueva:

| Copias del candidato | Puntuación | Decisión del motor de puntuación |
| --- | ---: | --- |
| 1 | 77,7 | `QUICK_REVIEW` |
| 2 | 90,2 | `AUTO_RENAME` |
| 3 | 90,2 | `AUTO_RENAME` |

La suma de pesos cuenta varias veces la misma evidencia. Hay deduplicación y
otras barreras de consenso en partes del flujo completo; esta prueba **no
demuestra que se renombrara un archivo incorrecto**. Sí demuestra que una
propiedad fundamental del motor no se cumple: repetir información no debería
aumentar la certeza.

Corrección: identificar evidencia por procedencia, registro y campo; limitar la
contribución repetida de una fuente; agrupar fuentes que copian el mismo registro;
aplicar contradicciones de edición, idioma, volumen e ISBN antes de permitir una
acción automática. El agrupamiento debe producir resultados deterministas, no
depender del orden de llegada.

Aceptación: duplicar o permutar candidatos no cambia la decisión; una edición o
traducción incompatible fuerza revisión; las barreras se prueban también a través
del flujo completo que prepara operaciones de archivos.

### F4 — P1 — Abrir otro almacén de planes altera trabajo activo

Ubicaciones: `core/operation_plans.py:54`, `core/operation_plans.py:116`,
`library_core.py:1170`.

El constructor convierte incondicionalmente elementos `running` a `pending` y
planes `applying` a `paused`. Se reprodujo manteniendo viva una primera instancia
y creando una segunda sobre la misma base. Se interpreta una reapertura como si
el trabajador anterior hubiera muerto. La exclusión actual es por instancia.

No se reprodujo una ejecución duplicada de movimiento. El defecto confirmado es
la modificación incorrecta de estados activos, que compromete coordinación y
recuperación.

Corrección: servicio único por perfil, bloqueo entre procesos para el escritor,
propietario de tarea y transición condicional de estados. Recuperar trabajo
interrumpido solo después de comprobar que ya no hay propietario válido. No
confundir inicialización del esquema con recuperación de una sesión caída.

Aceptación: abrir una segunda instancia no reinicia tareas vivas; una caída real
sí deja un plan recuperable; reintentar no ejecuta dos veces un paso confirmado.

### F5 — P1 — Límites de texto que no limitan realmente la lectura

Ubicaciones: `core/document_readers.py:42`, `:77`, `:91`, `:96`, `:106`.

Hay lecturas completas seguidas de un recorte: `read_bytes()[:limite]`. Un TXT de
12.000.000 bytes se leyó entero aunque el texto devuelto quedó limitado a
2.000.000 de caracteres. Las entradas ZIP y la captura de salida de procesos
también necesitan límites antes de materializar su contenido.

Esto no demuestra una explotación; sí demuestra que las constantes actuales no
son garantías de consumo máximo. Un archivo comprimido pequeño puede producir
mucho contenido descomprimido.

Corrección: lectura acotada desde el origen, presupuesto acumulado por documento,
límites de entradas ZIP y tamaño expandido, máximo de píxeles decodificados y
salida de subprocesos leída incrementalmente. Aislar lectores complejos con
tiempo y memoria máximos, conservando el original intacto al fallar.

Aceptación: archivos sobredimensionados y comprimidos adversariales terminan con
un error controlado sin crecimiento de memoria no acotado.

### F6 — P1 — Catálogo corrupto confundido con biblioteca vacía

Ubicación: `core/index_store.py:7`.

Un JSON incompleto devolvió `{"creado": null, "archivos": []}`. La misma salida
se usa para un primer arranque sin catálogo. El riesgo es que una escritura
posterior sustituya información recuperable por un catálogo vacío; esa pérdida
posterior no se ejecutó en la prueba.

Corrección: distinguir ausente, ilegible, corrupto y esquema incompatible;
preservar el archivo afectado; ofrecer restauración desde una copia verificada;
no permitir sobreescritura silenciosa. Mantener las escrituras atómicas existentes.

Aceptación: corrupción y errores de permisos muestran un estado de recuperación,
no un primer uso; restauración probada sobre una copia del perfil.

### F7 — P1 de uso — Las acciones de detalles pueden quedar fuera de la ventana

Ubicación: construcción del panel de detalles en `ui/workspace.py`.

En la ventana real con datos ficticios, los botones inferiores eran visibles sin
selección. Al seleccionar un libro, portada, metadatos y ruta ocuparon el alto
disponible y las acciones inferiores quedaron fuera del área visible, tanto en el
tema claro como en el oscuro.

Corrección: reservar una franja inferior para las acciones, ajustar la portada al
alto restante y agrupar metadatos secundarios en secciones plegables. Mantener
los laterales sin scroll, como se ha solicitado. En ventanas estrechas, abrir los
detalles como un panel alternativo con sus acciones siempre accesibles.

Aceptación: abrir, editar y copiar ruta accesibles con tamaños de ventana y
escalados habituales, incluso con títulos, rutas y etiquetas largos.

### F8 — P2 — El circuito de proveedores no se recupera si se consulta seguido

Ubicaciones: `metadata/external_providers.py:71`, `:81`, `:90`.

Después de registrar tres fallos, cada consulta rechazada por circuito abierto
actualiza la marca de tiempo usada para calcular el enfriamiento. En la prueba,
consultas a los segundos 50, 100, 150 y 200 mantuvieron el circuito abierto porque
cada una reinició el reloj.

Corrección: separar `opened_at`, `last_attempt_at` y `next_retry_at`; reloj
monótono; una única solicitud de prueba al salir del enfriamiento. Añadir límites
compartidos por proveedor, `Retry-After`, espera aleatoria controlada y plazo total
de la tarea. Dormir 0,20 segundos dentro de cada hilo no limita la tasa agregada.

Open Library publica límites de una petición por segundo sin identificación y
tres para solicitudes identificadas, junto con recomendaciones de caché y uso
moderado. La política debe comprobarse por API, no suponerse igual para todos los
servicios. [Guía oficial de APIs](https://openlibrary.org/developers/api).

Aceptación: el circuito vuelve a probar aunque haya consultas frecuentes; el
número agregado de solicitudes cumple la política configurada; la cancelación no
deja una cola ilimitada de peticiones pendientes.

### F9 — P2 — Tabla completa, reconstrucciones y trabajo previo en el hilo gráfico

Ubicaciones: `ui/workspace.py`, `library_app.py:1119`,
`core/operation_plans.py:120`.

La tabla termina cargando todas las filas. Además, al crear un plan de importación
se calculan hashes antes de entrar en la tarea de fondo: un lote grande puede
bloquear la interfaz antes de mostrar progreso. Esta última duración no se midió;
la ruta síncrona sí se localizó en el código.

Corrección: filas visibles más margen de precarga, modelos incrementales, hashes
fuera del hilo gráfico y tareas con generaciones que descarten resultados de
selecciones obsoletas. Conservar la revalidación inmediatamente anterior a cada
operación de archivo; mover el cálculo de hilo no autoriza a omitirla.

Aceptación: arrastre y búsqueda responden durante un escaneo; selección rápida
no muestra la portada de otro libro; la tabla no materializa 50.000 filas gráficas.

### F10 — P2 — Tema, accesibilidad y coherencia de estados

En la inspección visual se observaron fondos residuales en el indicador `Ctrl+K`
al cambiar de tema y parches de fondo en etiquetas del panel de detalles. El
árbol de automatización de Windows expuso principalmente paneles e imágenes sin
nombres suficientes para identificar varias acciones.

Esto exige pruebas reales de tecnología de asistencia. Una propiedad Python
llamada `accessible_name` no garantiza por sí sola que el sistema operativo
reciba un nombre accesible. No se hizo una sesión completa con NVDA.

Corrección: un sistema único de colores y estados, orden correcto de aplicación
del tema, roles y nombres accesibles, navegación por teclado, foco visible y
atajos consistentes. Probar todo ello con lectores de pantalla, no solo con
capturas o atributos internos.

## 5. Lenguajes y tecnologías

La pregunta útil no es qué lenguaje es más rápido en abstracto, sino qué parte
del programa necesita cambiar y qué evidencia justificaría ese coste.

| Opción | Ventaja para este proyecto | Coste o riesgo | Decisión |
| --- | --- | --- | --- |
| Python + Tkinter | Conserva lógica, pruebas y distribución; suficiente para corregir los fallos medidos | Controles personalizados, accesibilidad y composición visual requieren trabajo | Mantener durante estabilización |
| Python + PySide6 / Qt | Conserva el motor; modelos y vistas, controles y accesibilidad más estructurados | Migrar la interfaz, revisar licencias y rehacer pruebas y paquetes | Principal candidato para un prototipo |
| TypeScript + Tauri + motor Python | Libertad de interfaz web conservando parte del motor | Tres entornos, comunicación entre procesos y empaquetado por plataforma | No adoptar ahora |
| C# + Avalonia | Alternativa multiplataforma coherente si el equipo pasa a .NET | Portar motor y pruebas o conservar un puente con Python | Sin justificación suficiente hoy |
| Rust para componentes concretos | Útil si aparece un cuello de botella CPU bien aislado | Interoperabilidad, compilaciones y mantenimiento adicional | Solo después de perfilar |

Tk procesa eventos cooperativamente: las operaciones largas deben dividirse o
ejecutarse fuera de sus manejadores. Cambiar el intérprete o aumentar hilos no
arregla un guardado completo realizado desde un botón. [Modelo de eventos de Tkinter](https://docs.python.org/3.12/library/tkinter.html#threading-model).

Qt proporciona vistas basadas en modelos y mecanismos de accesibilidad que hacen
plausible una mejor base gráfica, pero eso no demuestra que una migración concreta
sea más rápida. Para empezar, conviene comparar `QListView` con delegados y
`QTableView`; evaluar QML únicamente si la composición y animación justifican su
complejidad. [QListView](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QListView.html),
[accesibilidad en Qt](https://doc.qt.io/qt-6/accessible.html).

Tauri permite incluir un ejecutable Python como proceso auxiliar, pero ese motor
debe empaquetarse para los destinos correspondientes. El menor tamaño de un shell
no implica automáticamente menor paquete total con Python y OCR incluidos.
[Procesos auxiliares en Tauri](https://v2.tauri.app/develop/sidecar/).

Avalonia admite Windows, macOS y Linux con distintos niveles de soporte según la
plataforma. La disponibilidad técnica no elimina el coste de portar el código
actual. [Plataformas de Avalonia](https://docs.avaloniaui.net/docs/supported-platforms).

Antes de distribuir Qt deben revisarse las licencias de los módulos elegidos y
sus condiciones de distribución; no asumir que todas las combinaciones tienen
las mismas condiciones. [Licencias de Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html).

### Condición para decidir una migración gráfica

Construir solo Biblioteca y Detalles con el mismo catálogo, las mismas portadas,
los mismos tamaños de ventana y el mismo servicio de datos. Comparar Tk
optimizado y Qt en Windows, Mac y Linux: latencia hasta presentación, arrastre,
memoria total, arranque frío, escalado, teclado, lector de pantalla y paquete.

Migrar si el prototipo resuelve una limitación demostrada y mantiene seguridad,
compatibilidad y mantenimiento asumible. Si Tk corregido cumple los objetivos,
continuar con Tk es una decisión válida. No mantener dos interfaces completas de
forma indefinida ni portar simultáneamente interfaz y persistencia.

## 6. Arquitectura y datos propuestos

El inventario de Python versionado contiene 105 archivos y 30.877 líneas,
incluyendo pruebas y herramientas. Tres archivos concentran gran parte del flujo:
`library_core.py` tiene 6.998 líneas; `library_app.py`, 2.677; y
`ui/workspace.py`, 2.676. El tamaño no prueba por sí solo un defecto, pero la mezcla
de responsabilidades sí dificulta pruebas y cambios pequeños.

Dirección propuesta:

```text
Interfaz y modelos de presentación
  └─ Servicios de catálogo, importación, revisión y recuperación
       ├─ Repositorio SQLite y migraciones versionadas
       ├─ Gestor de tareas, cancelación y progreso
       │    ├─ Trabajadores aislados de documentos, PDF y OCR
       │    └─ Clientes web con caché y límites por proveedor
       └─ Planes y transacciones de archivos con revalidación y cuarentena
```

La interfaz no debe decidir identidad, escribir bases de datos ni ejecutar
movimientos directamente. Consume resultados tipados y emite comandos. Los
servicios no deben importar Tk ni depender de variables globales de la ventana.

### Una autoridad para el catálogo

Hoy SQLite se alimenta del JSON y parte de la interfaz vuelve a consultar la
proyección SQL. La solución es una autoridad inequívoca, no dos copias que intentan
corregirse entre sí silenciosamente.

Migración propuesta:

1. Crear una copia consistente del perfil y registrar versión, conteos y huellas.
2. Importar a una base nueva sin alterar el índice anterior.
3. Verificar registros, relaciones, etiquetas, favoritos, correcciones humanas y
   referencias a planes, cuarentena e historial.
4. Activar la nueva autoridad mediante un cambio de versión de perfil explícito.
5. Conservar el estado previo para recuperación; impedir que una versión antigua
   escriba inadvertidamente un perfil de esquema nuevo.
6. Convertir JSON en exportación o compatibilidad explícita, no un segundo maestro.

Las copias de una base SQLite activa deben realizarse con mecanismos consistentes
como la API de backup, no copiando únicamente el archivo principal mientras hay
escrituras WAL. Un respaldo del catálogo no equivale a un respaldo de los libros.
[API de backup de SQLite](https://www.sqlite.org/backup.html).

### Identidades estables

Los identificadores actuales de obra dependen de título y autor normalizados;
los de edición dependen de esos datos y otros campos. Corregirlos puede producir
otra identidad, aun tratándose del mismo objeto bibliográfico.

Usar identificadores persistentes independientes del texto, con operaciones
explícitas de unir o separar obras y ediciones. Añadir identidad de biblioteca y
escaneo. Separar relación de archivo, edición, obra, contribuyente, colección y
progreso de lectura. No fusionar ediciones únicamente porque compartan título.

La consulta actual en memoria ya es rápida. Adoptar índices SQL y, si las
necesidades de consulta lo justifican, FTS5; no cambiar semántica de búsqueda sin
pruebas de acentos, frases, prefijos y subcadenas. La búsqueda por tokens no es
equivalente a buscar una subcadena. [FTS5](https://www.sqlite.org/fts5.html).

### Tareas y cancelación

Usar una cola limitada, prioridades y propietario de tarea. Prioridad alta para la
portada seleccionada y la ventana visible; baja para precarga y enriquecimiento.
Evitar lanzar una futura tarea por cada libro de una biblioteca enorme.

Cancelar debe impedir nuevas tareas y comunicar inmediatamente el estado. Los
trabajadores nativos necesitan límites efectivos: cancelar un `Future` no detiene
una función ya en ejecución. Separar cancelación solicitada, cancelación efectiva
y recuperación de operaciones parciales. [Cancelación en concurrent.futures](https://docs.python.org/3.12/library/concurrent.futures.html).

## 7. Algoritmos de identidad y duplicados

### Decisión única y explicable

Existen varias capas de puntuación y consenso. Consolidarlas detrás de un contrato
único de decisión: propuesta, evidencia por campo, contradicciones, procedencia,
acción permitida y motivo. Conservar módulos especializados de extracción, no
varias autoridades que interpreten de manera distinta un porcentaje.

Los porcentajes actuales son puntuaciones heurísticas, no probabilidades
estadísticamente calibradas. La interfaz debe decir «evidencia alta»,
«confirmado por ti» o «requiere revisión» cuando corresponda, sin presentar 90 %
como garantía de acierto. Una corrección de autor tampoco confirma necesariamente
todos los campos de la edición.

Reglas indispensables:

- Duplicar evidencia no aumenta confianza.
- Reordenar resultados no cambia la identidad elegida.
- La ausencia de datos no equivale a confirmación.
- Misma obra no implica misma edición, traducción o volumen.
- Una corrección humana tiene procedencia y bloqueo por campo.
- Una contradicción relevante fuerza revisión, aunque la puntuación sea alta.
- Una propuesta de IA no autoriza por sí misma renombrar, reemplazar o descartar.

### Reducir comparaciones antes de acelerar la función de similitud

El motor ya agrupa candidatos, pero los grupos basados en claves poco selectivas
pueden seguir siendo grandes. Priorizar índices de ISBN validado, idioma, autor
normalizado, número de volumen y tokens distintivos. Comparar solo un conjunto
acotado de candidatos y conservar una ruta de revisión para lo incierto.

Para duplicados exactos: agrupar por tamaño; usar firmas parciales solo como
filtro; calcular SHA-256 completo para confirmar igualdad. Revalidar la identidad
del archivo inmediatamente antes de cualquier mutación, incluso si existe una
huella en caché. Nunca declarar equivalencia por firma parcial o título.

RapidFuzz merece una comparación controlada frente a `SequenceMatcher`, con
normalización precalculada y límites de candidatos. Cambiar de métrica obliga a
recalibrar umbrales: las puntuaciones no son intercambiables. Evitar una matriz
global de todas las parejas, cuyo tamaño crece cuadráticamente.
[Procesamiento de candidatos en RapidFuzz](https://rapidfuzz.github.io/RapidFuzz/Usage/process.html).

### Corpus y evaluación

Ampliar las pruebas actuales con un corpus versionado, sintético o redistribuible,
de unas 300–500 situaciones iniciales: títulos parecidos, ediciones incompatibles,
autores homónimos, traducciones, volúmenes, compilaciones, ISBN inválidos, OCR
ruidoso y fuentes repetidas. Separar ajuste y evaluación.

Medir precisión de las propuestas automáticas, cobertura, revisiones necesarias,
falsos duplicados y tiempo por libro. Exigir cero operaciones inseguras en los
casos adversariales de aceptación. Ese corpus inicial no demuestra por sí solo
una tasa universal de error extremadamente baja; la incertidumbre debe seguir
enviándose a revisión.

## 8. OCR, documentos, portadas y red

### OCR y extracción

Mantener Tesseract como base y los contenidos locales. Hacer una extracción
progresiva: metadatos internos, páginas de identificación, OCR selectivo y, solo
si falta evidencia, un análisis más costoso. Reutilizar el documento abierto
dentro de un trabajador para evitar abrir y renderizar repetidamente lo mismo.

La aplicación ya incorpora variantes de resolución; la siguiente mejora debe
evaluar selección de páginas, idioma, rotación, segmentación y calidad sobre el
corpus, no simplemente aumentar DPI para todo. La documentación de Tesseract
explica la influencia de resolución, ruido y segmentación. [Calidad de Tesseract](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html).

PaddleOCR u otro motor puede evaluarse como alternativa opcional para documentos
difíciles, pero no debe sustituir al motor actual por resultados publicados en
otros conjuntos de datos. Comparar precisión, CPU, RAM, tamaño de distribución y
licencias antes de añadirlo. No incorporar modelos pesados al paquete básico sin
una ventaja medida en esta biblioteca.

### Portadas eficientes

Mantener URL y procedencia en el catálogo, miniaturas en una caché de disco
limitada y únicamente imágenes visibles más una pequeña precarga en RAM. Una
imagen mostrada siempre necesita memoria temporal; el objetivo realista es no
mantener todas las portadas decodificadas.

La implementación actual ya tiene una base útil de caché y límites de descarga.
Mejorarla con claves por versión del archivo, tamaño y escala; solicitudes
compartidas para la misma portada; cancelación de resultados obsoletos; prioridad
de selección; estados claros de ausencia y error; límites de píxeles además de
bytes. Reescalar al finalizar el arrastre o a intervalos acotados, no decodificar
de nuevo en cada movimiento de la división.

Una portada remota no debe identificar por sí misma una edición. Mantener un
marcador visual cuando la imagen es genérica, corresponde a otra edición o tiene
procedencia incierta. No depender de conectividad para abrir la biblioteca.

### Privacidad y proveedores

Separar claramente «OCR local» de «consulta bibliográfica en Internet». Aunque no
se suban páginas, una consulta por ISBN, título o autor comunica esos términos al
proveedor. Mostrar qué funciones usan red, permitir modo sin conexión y no enviar
rutas locales, textos completos o títulos en informes públicos de diagnóstico.

Un cliente central por proveedor debe controlar tasas, caché, reintentos,
caducidad, tamaño, cancelación y errores. Validar destinos de red y redirecciones
antes de permitir contactos fuera de la política establecida. Los registros deben
ser útiles sin convertirse en una copia pública de la biblioteca personal.

## 9. Disposición visual y experiencia

### Conservar el estilo elegido

Mantener marfil y terracota en claro, superficies oscuras cálidas en oscuro,
tipografía editorial para títulos y tipografía de interfaz legible para controles.
Conservar una familia de iconos de trazo consistente y las dimensiones aprobadas.
No añadir más sombras, transparencias o animaciones sin una función clara.

Centralizar colores, espaciado, radios, tamaños de icono y estados de foco,
selección, pulsación, error y deshabilitado. Resolver el dibujo y antialiasing a la
escala de pantalla; no recomponer bordes redondeados en cada evento de ratón.

### Composición recomendada

- **Izquierda:** navegación estable, con Importar y explicaciones breves en las
  secciones principales; configuración y ayuda abajo. Sin scroll lateral.
- **Centro:** búsqueda protagonista, filtros y ordenación inmediatamente debajo;
  resultados y selección con desplazamiento central. Estado y progreso sin tapar
  el contenido.
- **Derecha:** título, autor interactivo, favorito y portada adaptable; serie y
  etiquetas editables; edición, archivo y procedencia en grupos plegables;
  acciones inferiores fijas. Sin scroll lateral.
- **Ventana estrecha:** detalles en un panel alternativo o diálogo, manteniendo
  contexto y selección. No comprimir tres columnas hasta hacerlas ilegibles.

La ruta completa debe ser seleccionable, copiable y accesible por teclado. Si el
espacio obliga a mostrarla abreviada en reposo, la expansión debe mostrarla entera
sin depender exclusivamente de un tooltip. Abrir ubicación y copiar ruta deben
seguir disponibles aun con metadatos largos.

### Interacciones

La búsqueda debe conservar foco, texto, selección y filtros al cambiar entre
tabla y portadas. Usar una espera breve para agrupar pulsaciones, sin ejecutar
trabajo pesado dentro del manejador. Mostrar cantidad de resultados y distinguir
biblioteca vacía, búsqueda sin coincidencias y error de lectura.

Reutilizar tarjetas y filas. Actualizar únicamente las celdas o tarjetas afectadas
por favoritos, etiquetas y progreso. Durante el arrastre de divisiones, separar
el cambio de geometría de la regeneración de miniaturas. Mantener límites mínimos
de anchura y restaurar proporciones de forma compatible con el tamaño actual.

Mostrar puntero de mano solo donde existe una acción. Definir foco visible y
estados de teclado equivalentes al ratón. La coherencia importa más que añadir
efectos de hover a todos los elementos.

### Accesibilidad y escalado

Probar teclado completo, tamaños de texto, escala del sistema, alto contraste y
lector de pantalla. Como referencia de diseño, usar contraste de 4,5:1 en texto
normal y 3:1 en texto grande y elementos gráficos pertinentes; no depender solo
del color para indicar estado. WCAG es una referencia útil, no una certificación
automática de una aplicación de escritorio. [WCAG](https://www.w3.org/TR/wcag/).

Probar ventanas de 1024×768, 1366×768 y 1920×1080, junto con escalados de 100 %,
125 %, 150 % y 200 %. Los tamaños son escenarios de prueba, no promesas de que
las tres columnas completas cabrán siempre: a menor espacio debe activarse el
modo alternativo de detalles.

## 10. Dirección de producto

### Qué problema debe resolver mejor

La ventaja no debería ser «hacer todo lo que hace Calibre». Calibre ya reúne
gestión, metadatos, búsqueda, visualización y conversión. La oportunidad aquí es
una organización más comprensible y conservadora: descubrir qué libro es,
explicar la propuesta, permitir corregirla y aplicar cambios recuperables con una
interfaz menos abrumadora. [Manual de Calibre](https://manual.calibre-ebook.com/).

Priorizar a la persona con una colección local desordenada que necesita confiar
en lo que sucederá. Las métricas de producto deberían incluir tiempo hasta abrir
el primer libro, claridad del primer análisis, proporción de revisiones resueltas
y éxito de recuperación; no solamente cantidad de proveedores o formatos.

### Funciones que faltan o deben completarse

1. **Primer uso inequívoco.** Explicar catalogar una carpeta existente, copiar
   libros a una biblioteca y reorganizar físicamente. No presentar esas acciones
   como equivalentes. Preferir catalogar sin mover; cuando haya importación física,
   ofrecer copia como opción segura y movimiento explícito.
2. **Previsualización real.** Analizar sin modificar, mostrar origen, destino,
   campos anteriores y propuestos, motivo y reversibilidad; confirmar después.
   El diálogo actual de importación muestra nombres originales y pregunta aplicar
   antes de disponer de todo el resultado bibliográfico.
3. **Revisión como bandeja de trabajo.** Filtrar por contradicción, edición,
   duplicado posible o falta de evidencia; comparar propuestas y aplicar una
   decisión con trazabilidad. Persistir estado y progreso.
4. **Copias y restauración comprensibles.** Distinguir copia del catálogo, del
   perfil completo y de los libros. Verificar una restauración antes de anunciar
   que el usuario está protegido.
5. **Lectura y organización cotidiana.** Completar estado Por leer / Leyendo /
   Leído, filtros guardados y vistas de autores y series como entidades, no solo
   filtros sobre la misma lista. Definir si progreso corresponde a obra o edición.
6. **Interoperabilidad.** Exportar metadatos y colecciones en formatos documentados;
   conservar apertura con el lector preferido. Evaluar OPDS después, si aparece
   una necesidad real de dispositivos o lectores externos.
7. **Diagnóstico entendible.** Explicar proveedor no disponible, archivo no
   encontrado, formato no soportado, OCR insuficiente y conflicto bibliográfico;
   no agruparlos todos bajo un único resultado vacío.

Posponer sincronización cloud, funciones sociales, conversor universal, lector
completo propio y una IA autónoma que reorganice archivos. Amplían mantenimiento
y riesgos antes de resolver las debilidades medidas del flujo principal.

## 11. Calidad, distribución y mantenimiento

### Código y contratos

Extraer responsabilidades por casos de uso, no dividir archivos solo para reducir
su número de líneas. Empezar por catálogo, trabajos, importación y decisiones de
identidad. Introducir tipos en fronteras, contratos de errores y resultados
estructurados. Añadir lint y comprobación de tipos de forma gradual para evitar
mezclar una corrección de seguridad con un reformateo masivo.

No borrar pruebas, cuarentena, historial, planes, perfiles o respaldos bajo la
etiqueta de limpieza. Los archivos generados y paquetes deben tener destinos
claros y una política de retención; los ejecutables siguen siendo artefactos de
release, no contenido del historial Git.

### Pruebas que deben añadirse

- Propiedades del motor de identidad, incluidas repetición y orden de fuentes.
- Fallos a mitad de transacción: espacio insuficiente, permisos, archivo cambiado,
  destino ocupado, caída entre fases y fallo del propio Undo.
- Dos instancias sobre el mismo perfil y recuperación de un propietario muerto.
- Catálogo de 50.000 y 100.000 filas, favorito y edición de un único registro.
- Documentos con límites adversariales y trabajadores que no responden.
- Fluidez con tareas de fondo y portadas frías, no solo filtros preparados.
- Teclado, accesibilidad y geometría de acciones en las tres plataformas.
- Primer uso, actualización con perfil existente y desinstalación que conserva
  datos conforme a la opción elegida.

### Integración y entrega

Las validaciones de Windows y de fuentes en Mac/Linux son una buena base. Los
controles multiplataforma examinados no sustituyen una sesión gráfica y una
instalación reales. Ampliar la matriz con pruebas de interfaz y las condiciones
que hoy faltan en los benchmarks.

Mantener versiones bloqueadas y huellas de dependencias; revisar diferencias
entre plataformas. Fijar acciones de CI a revisiones verificadas, limitar permisos
y automatizar avisos de actualización, análisis de dependencias y un inventario de
componentes distribuidos. No se afirma que exista una vulnerabilidad conocida:
esa comprobación específica queda pendiente.

Unificar revisión de origen y manifiestos para todos los paquetes de una futura
release. No sobrescribir tags ni activos ya publicados. Los paquetes actuales
documentan limitaciones de firma; firma Windows y firma/notarización de macOS
deben tratarse como trabajo de distribución con credenciales y costes propios,
no como una casilla que se obtiene al compilar.

No se encontró un archivo `LICENSE` del proyecto entre los archivos versionados.
Debe elegirse y documentarse una licencia del código, además de los avisos de
terceros, antes de presentar el proyecto como reutilizable bajo unas condiciones
concretas. Esa decisión corresponde al propietario; no se selecciona una licencia
ni se cambian derechos de distribución en esta auditoría.

## 12. Plan de ejecución

Los bloques tienen dependencias y criterios de salida. Los tamaños relativos son
orientativos: pequeño suele afectar una frontera y sus pruebas; mediano afecta
varios módulos; grande implica migración o cambio de experiencia. No son una
estimación contractual de duración.

| Bloque | Entrega | Tamaño | Condición para continuar |
| --- | --- | --- | --- |
| 1. Estabilidad | F1–F6, exclusión PDFium, recuperación de planes, errores explícitos y límites reales | Mediano–grande | Casos reproducidos convertidos en regresiones; ninguna mutación insegura |
| 2. Fluidez inmediata | Acciones de detalles fijas, favoritos fuera del hilo gráfico, tema coherente, hashing de importación asíncrono | Mediano | Ventana utilizable durante persistencia y análisis |
| 3. Datos y trabajos | Autoridad SQLite, actualizaciones por registro, IDs estables, migración y restauración, cola limitada | Grande | Paridad de perfil, recuperación y pruebas de carga verificadas |
| 4. Identidad y red | Decisión única, procedencia, corpus, contradicciones, circuito y límites por proveedor | Mediano–grande | Métricas y propiedades de seguridad aprobadas |
| 5. Experiencia | Previsualización antes/después, revisión persistente, primer uso, vistas y accesibilidad | Grande | Flujos completos con teclado y tamaños de pantalla reales |
| 6. Decisión gráfica | Prototipo Biblioteca + Detalles en Qt contra Tk optimizado | Mediano y acotado | Comparación de rendimiento, accesibilidad, empaquetado y mantenimiento |
| 7. Publicación | Paquetes coherentes, validación de instalación/actualización, licencias y diagnóstico | Mediano | Manifiestos y evidencias reales por plataforma |

La corrección del circuito F8 puede adelantarse como cambio pequeño independiente.
Los defectos visuales graves tampoco necesitan esperar a la migración de datos.
Una migración completa a Qt, si se decide, sería un proyecto posterior al
prototipo, no parte implícita del bloque 6.

### Objetivos medibles propuestos

Estos son criterios a validar, no resultados ya conseguidos:

- Favorito: respuesta visual en menos de 50 ms; persistencia p95 inferior a
  100 ms con 10.000 registros y a 200 ms con 50.000, sin reescritura global.
- Búsqueda: cálculo p95 inferior a 50 ms; entrada a presentación inferior a
  200 ms incluyendo espera breve y dibujo.
- Fluidez: ningún guardado o hash largo en el hilo gráfico; callbacks habituales
  por debajo de 16–33 ms y detección de pausas superiores a 50 ms.
- Cancelación: confirmación visual inferior a 100 ms; cada operación nativa o de
  red con un plazo explícito. Informar si un trabajador sigue terminando.
- Escala: 100.000 registros sin desbordar parámetros SQL; memoria de controles e
  imágenes relacionada con lo visible, no con una imagen por libro.
- Recuperación: ningún original perdido en las pruebas de fallo; catálogo,
  correcciones, planes y cuarentena restaurados y verificados.
- Accesibilidad: acciones esenciales operables con teclado y expuestas con nombre
  y rol al sistema; sin botones inaccesibles por geometría.

Repetir benchmarks con calentamiento, al menos 100 muestras para percentiles de
interacción y medición separada de arranque frío, RAM total y carga de CPU. Registrar
máquina, revisión y dependencias para que las comparaciones tengan sentido.

## 13. Reproducción y siguiente paso

Desde la raíz del repositorio público, con las dependencias del entorno instalado:

```powershell
python -B -m unittest discover -s tests -v
python -B tools/benchmark_catalog.py --sizes 1000 10000 50000 --repetitions 7 --memory --check
python -B tools/benchmark_ui.py --size 10000
python -B tools/benchmark_ui.py --size 50000
python -B tools/benchmark_ui.py --size 120 --preview
```

Las sondas adicionales de esta auditoría usaron una base temporal nueva para cada
tamaño y tres cambios sucesivos de favorito; un PDFium simulado para detectar
solapamiento; reloj simulado para el circuito; dos almacenes sobre un mismo plan;
un TXT sintético de 12 MB; JSON deliberadamente incompleto; y un candidato externo
repetido una, dos y tres veces. No requieren una biblioteca personal ni consultas
reales a proveedores. Deben trasladarse a pruebas de regresión junto con cada
corrección, conservando el comportamiento seguro como criterio de aceptación.

**Siguiente paso recomendado:** implementar el bloque 1 con pruebas que fallen
antes de cada corrección y pasen después, manteniendo la versión pública actual
intacta hasta validar el conjunto. En paralelo de prioridades, corregir el acceso
a los botones de detalles. La decisión de lenguaje y framework debe apoyarse en
la comparación posterior, no preceder a estas correcciones.
