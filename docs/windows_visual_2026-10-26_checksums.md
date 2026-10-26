# Revisión visual y de usabilidad — 2026-10-26

Revisión de desarrollo de `codex/audit-optimizations`. No constituye una nueva
versión publicada, una aprobación global de redistribución ni una certificación
de accesibilidad. Conserva el estilo cálido, los iconos de trazo y la aplicación
Python/Tk existente.

## Fuente y alcance

- Código validado: `36834b4a63d3045b8f99f369fedb04b19b57e767`.
- Referencia anterior a esta revisión: `43b5236`.
- Huella local de fuentes relevantes para build: 283 archivos,
  `CF6383890708B38C0E1CC6A739BD3D92E422C15A9210AA008E4FC9D412F4D664`.
  Los manifiestos de CI identifican los bytes construidos en sus propios hosts;
  los finales de línea pueden producir huellas diferentes.
- Perfiles, portadas y catálogos sintéticos y temporales. No se usó la biblioteca
  personal ni se instalaron los cambios sobre la instalación habitual.
- Biblioteca, autores, series, etiquetas, favoritos, importar, revisiones,
  actividad, configuración y la vista previa de operaciones.

Este informe derivado se excluye de la huella mediante la regla existente para
`docs/windows_*_checksums.md`; no cambia el código de los paquetes probados.

## Cambios aplicados

- Búsqueda con icono de la paleta compartida, botón accesible para borrar,
  Escape y menos refrescos redundantes. Los resultados vacíos ofrecen recuperar
  todos los libros y desactivan las acciones sobre una selección anterior.
- Cuadrícula que admite una columna, dimensiones de portada en píxeles incluso
  antes de cargar la imagen y borde de selección de grosor constante. Cambiar de
  libro no altera el tamaño de las tarjetas.
- Detalles con ruta completa seleccionable, copiar y abrir carpeta; acciones y
  relaciones se compactan cuando falta espacio. Favorito, autor, serie y
  etiquetas conservan nombres accesibles y ayudas con sus valores completos.
- Solo se conserva una imagen de la portada seleccionada para detalles, sin
  una segunda copia a tamaño completo. Las imágenes inválidas quedan reintentables.
- Panel de detalles ocultado manualmente permanece oculto al redimensionar.
  La barra lateral reduce decoración antes de recortar navegación o tema.
- Cabeceras, ajustes, selección de carpeta y grupos de botones se adaptan al
  ancho real. Los cuatro pasos de importación pasan a dos filas equilibradas.
- La cabecera reserva una columna para el idioma y otra para el título; ya no
  oscila de altura al envolver textos grandes. La marca y la navegación ajustan
  su fuente al ancho disponible. Los controles inferiores de voz miden sus
  etiquetas, se distribuyen en dos filas si hace falta y reservan la altura
  necesaria. El botón Cancelar también conserva su texto completo.
- Texto y controles medidos con la fuente real, ayudas de carpeta corregidas y
  fuentes serif alternativas disponibles en Linux. La opción de tema por defecto
  tiene una etiqueta independiente del sistema operativo.
- Búsqueda y títulos sin marcos oscuros internos innecesarios; foco de teclado
  visible. Divisiones visualmente discretas conservan un área de arrastre de
  siete píxeles. Colores de desplegables desactivados comprobados en claro,
  oscuro y alto contraste.
- La aplicación de tema evita configurar dos veces los botones de cada libro.
  Los bordes de selección solo se configuran cuando cambia su estado o paleta.
- Cambiar de idioma recalcula el tamaño de los botones de contenido, actualiza
  Filtros y Cancelar y conserva completa la palabra Siguiente. La paginación
  mide sus etiquetas y evita reconfigurarlas si no cambian.
- Las páginas desplazables actualizan su región solo cuando cambia y vuelven
  a mostrar el control enfocado al cambiar las dimensiones del contenido o del
  visor, conservando la navegación por teclado durante la redistribución.

## Verificación local

- `python -B -m unittest discover -s tests`: **796 pruebas, sin fallos**, siete
  omitidas; 14,500 segundos. No se contabilizan las omisiones como aprobadas.
- Ruff: `E9,F63,F7,F82,F401,F811,F841`, correcto; `git diff --check`, correcto.
- `tools/verify_workspace_layout.py`: **84 casos de distribución y 19
  comprobaciones de interacción**, todos correctos, sin excepciones de Tk.
  Cada escala utiliza un proceso nuevo.
- Ventanas entre 760 × 560 y 1920 × 1080; escalado de texto Tk de 100, 125,
  150 y 200 %. Esto no equivale a probar el DPI real de cada sistema operativo.
- Ocho casos adicionales verifican las etiquetas de navegación, marca, voz,
  paginación, agregar libros y filtros en español, inglés, francés y chino,
  al 100 y al 200 %. Se comprueba que el texto
  cabe, además de la posición de los widgets. No se activó la voz para medirlos.
- Se comprobaron búsqueda vacía, recuperación de filtros, selección de autores,
  filtro guardado, contraste, ruta completa, imágenes inválidas, detalles ocultos
  y una sola portada retenida para detalles. La vista previa expuso 1.005 filas
  paginadas y ocho campos de comparación, sin cambiar originales sintéticos.
- Las comprobaciones asíncronas esperan condiciones observables con un límite
  de tres segundos; no presuponen que una carga o una redistribución terminen
  exactamente tras una pausa fija.
- Sonda adicional de redistribución: cinco comprobaciones correctas con Tk
  real y una identidad de foco inyectada. El cambio de contenido y del visor
  revela el control; el desplazamiento manual se conserva; enfocar navegación
  no arrastra la página; no hubo excepciones. No es una prueba de teclado del
  escritorio ni de un lector externo.

## Rendimiento medido

Dos ejecuciones secuenciales, con el mismo Python/Tk, 4.158 registros sintéticos
y veinte repeticiones de cada acción. La referencia usa la misma herramienta
de medida corregida que el código actual: p95 por rango más cercano. El antiguo
cálculo de p95 omitía el extremo lento en lotes pequeños; ya está corregido y
tiene regresiones. No se mezclan las mediciones con otras pruebas locales.

La herramienta de medida actual y su copia en la referencia tienen el mismo
SHA-256: `E26B82DD7412EEBFE1565D15135C12B70711FC029078C58C42E1A7E4DDD3E2C6`.

| Acción | Mediana anterior → actual, ms | p95 anterior → actual, ms |
| --- | ---: | ---: |
| Refrescar portadas | 9,27 → 9,05 | 13,26 → 10,53 |
| Página siguiente | 18,63 → 15,52 | 20,87 → 16,64 |
| Página anterior | 18,65 → 14,66 | 23,18 → 16,42 |
| Redistribuir cuadrícula | 0,16 → 0,22 | 0,17 → 0,28 |
| Desplazar división | 0,02 → 0,03 | 0,02 → 0,03 |
| Vista de tabla | 6,41 → 4,91 | 7,15 → 6,03 |
| Vista de portadas | 16,01 → 12,05 | 18,00 → 13,12 |
| Cambiar tema | 24,51 → 29,00 | 29,80 → 31,13 |
| Seleccionar libro | 4,65 → 4,87 | 6,09 → 5,30 |
| Despachar favorito | 2,39 → 2,89 | 3,11 → 3,42 |
| Guardar favorito hasta completar | 89,19 → 96,34 | 96,21 → 118,29 |

No hay una aceleración universal: favoritos y cambio de tema cuestan más en
esta muestra. Los callbacks medidos no superaron 50 ms; el intervalo máximo de
la sonda de eventos fue 75,72 → 67,62 ms. Esto no mide FPS, repintado completo
del escritorio ni arrastre manual con el ratón.

RSS al terminar: 107,04 → 104,86 MiB; pico: 107,44 → 111,38 MiB. Ambas
ejecuciones conservaron 30 tarjetas y 30 filas cargadas. CPU de todo el proceso
durante las interacciones: 19,61 s en 26,62 s → 26,73 s en 26,60 s de ensayo; no es CPU
exclusiva del hilo gráfico. Una sonda separada de reposo, tras estabilizar,
registró 0,0 s de incremento de CPU en una ventana de dos segundos para la fuente
actual, sin callbacks de ajuste de geometría. El resultado breve del contador
no equivale a consumo nulo ni mide autonomía o consumo global.

SHA-256 de la evidencia local, conservada fuera del repositorio:

| Informe | SHA-256 |
| --- | --- |
| `performance-baseline-20.json` | `C27B8EF6C117E4FCBD377604444849FF25379A1B0DF84FCDCE48C4E7258FDCA3` |
| `performance-reviewed-flow-20.json` | `72172ED24257D0A17E060F45E5891B641EF9C56E1C2742F8EBE984A073B3BF4A` |
| `usability-reviewed-flow.json` | `B8E223C36DC7E8A6C3BE670400F85F567CAAC3DF4DA3E5A5BA9E8B4D0DF41B2B` |
| `focus-reflow-reviewed.json` | `30D15D09B8FAD4F4D8831B7B0EF2BEEF1413238BABD4415F8D60D4451BFF32B4` |
| `idle-reviewed-flow.json` | `56115FCECB467861C215B03EFB9BD7E6BBC9AD059C32E94C75063CFB3E101F5D` |

## Validaciones remotas de esta fuente

Todas terminaron correctamente para `36834b4`:

| Ejecución | Resultado |
| --- | --- |
| [Fuente en macOS y Linux](https://github.com/erzod31/ManageYourLibrary/actions/runs/40320990014) | Correcto |
| [Windows: tests, corpus OCR y build canónico](https://github.com/erzod31/ManageYourLibrary/actions/runs/40320990254) | Correcto; job `121565572628` |
| [Nativos macOS/Linux](https://github.com/erzod31/ManageYourLibrary/actions/runs/40320990038) | Linux x64, macOS ARM64 e Intel correctos; publicación omitida |

Jobs nativos: Linux `121565746267`, macOS Intel `121565746535`, macOS ARM64
`121565746977`. Cada host pasó su matriz de 84 casos; los informes permanecen en
sus artefactos `workspace-layout-*`. Los builds congelados y los diagnósticos de
los workflows también pasaron. El artefacto Windows es la aplicación sin
empaquetar, no una validación nueva de instalación o actualización.

Se inspeccionaron ocho capturas de la interfaz real de Linux en el visor Xvfb
aislado de CI: biblioteca clara, oscura, en español, al 200 %, importar,
revisiones, actividad y configuración. Los libros y las portadas son sintéticos.
Archivo verificado: `workspace-layout-linux-x64`, ID `12648753251`, ZIP de
491.994 bytes; SHA-256
`A45B4AD9877F49C3EF64FF2161C768590638702B5FE8B3B619CBCA6CB2C7967F`.
Se comprobaron el digest, CRC y las rutas antes de extraer los PNG y el JSON.

## Límites de la revisión

La inspección manual de la aplicación sobre el escritorio Windows quedó
pendiente al encontrarse la pantalla de bloqueo. La comprobación automática de
geometría Tk no sustituye esa inspección. No se activaron NVDA ni voz audible.
La revisión de lectores de pantalla, el ciclo de instalación/actualización y
las comprobaciones de licencias de revisiones anteriores conservan su alcance
propio; no se atribuyen automáticamente a esta fuente.

No se crearon releases ni tags y no se fusionó `main`. La elegibilidad de
redistribución de Microsoft sigue sin determinarse y la aprobación global de
licencias sigue incompleta; superar una prueba de UI no modifica esas condiciones.
