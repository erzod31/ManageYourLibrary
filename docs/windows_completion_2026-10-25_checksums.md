# Cierre de comprobaciones Windows — 2026-10-25

Evidencia de desarrollo, no una versión pública nueva ni certificación de
accesibilidad completa. Las publicaciones existentes y el repositorio privado
se conservan. El usuario autorizó una prueba breve de voz local y NVDA portátil;
no autorizó instalar el lector ni añadirlo al inicio.

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

La reconstrucción final del EXE, el instalador y la validación de los paquetes
se registrarán aquí únicamente después de ejecutarse. No se sustituye esa
evidencia por los nombres de artefactos simulados que imprimen las pruebas unitarias.
La revisión global de redistribución, la firma de código, una matriz completa
de DPI y VoiceOver/Orca no quedan aprobados por esta sesión de NVDA.

Referencias primarias: [guía de NVDA](https://api.nvaccess.org/documentation/userGuide.html#SpeechViewer),
[salida SAPI a un stream](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ms723597(v=vs.85)).
