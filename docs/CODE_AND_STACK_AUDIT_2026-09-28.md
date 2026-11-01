# Auditoría de limpieza y adecuación tecnológica

Fecha: 2026-09-28

## Decisión ejecutiva

La aplicación está bien encaminada con **Python como lenguaje principal**. No hay
evidencia técnica que justifique reescribir el núcleo en C#, Rust, C++ o
TypeScript. La lógica de identidad bibliográfica, OCR, lectura de documentos,
planes recuperables, cuarentena y almacenamiento ya tiene una inversión grande
en Python y una cobertura de regresión valiosa.

La parte que debe vigilarse no es Python, sino **Tkinter como capa visual**.
Tkinter sigue siendo suficiente para la versión actual si la interfaz permanece
modular, virtualiza el trabajo visible y delega las tareas largas. Si el producto
necesita accesibilidad de nivel comercial, colecciones muy grandes, animaciones,
múltiples ventanas complejas o un acabado nativo más profundo, la evolución más
segura sería **mantener el núcleo Python y sustituir gradualmente la vista por
PySide6/Qt**.

Por tanto:

1. Mantener Python, SQLite, Tesseract, pypdf/pypdfium2, Pillow y PyInstaller.
2. Mantener Tkinter a corto plazo; no iniciar una reescritura preventiva.
3. Reducir primero los monolitos y formalizar la frontera entre vista y núcleo.
4. Evaluar PySide6 únicamente contra métricas y requisitos concretos.
5. No introducir Rust/Tauri o C#/WinUI mientras no exista una decisión explícita
   de producto que compense el coste y el riesgo de migración.

## Alcance y fotografía actual

La inspección se hizo sobre el árbol de trabajo actual, no sobre afirmaciones
históricas. En esta fecha el código contiene:

- 77 ficheros Python y unas 27.240 líneas, incluidas 5.553 líneas de pruebas.
- 21 módulos Python en la raíz, 17 en `core`, 4 en `metadata`, 3 en `ui`, 6 en
  `tools` y 26 en `tests`.
- Tres concentraciones todavía grandes: `library_core.py` (7.172 líneas),
  `library_app.py` (2.632 después de la limpieza) y `ui/workspace.py` (2.349).
- Persistencia local mediante SQLite y compatibilidad con datos JSON existentes.
- OCR local mediante Tesseract y procesamiento PDF con pypdf/pypdfium2.
- Distribución Windows mediante PyInstaller en modo de carpeta e Inno Setup.
- Scripts separados para Linux y macOS, pero sin prueba de lanzamiento nativa en
  esta máquina; su existencia no equivale a una versión validada.

Los ficheros `.bat`, `.ps1`, `.sh`, `.iss` y `.spec` son lenguajes de
automatización y empaquetado, no una segunda arquitectura de la aplicación. Los
DLL y datos de Tesseract son dependencias nativas necesarias para que el OCR siga
siendo local y no deben considerarse residuos.

## Limpieza realizada

La limpieza fue conservadora y no tocó libros, catálogo, configuración,
cuarentena, historial, copias, planes pendientes ni correcciones humanas.

- Se retiró `dist`, que ocupaba aproximadamente 626 MB y era completamente
  regenerable. El instalador final ya entregado se conservó fuera del árbol de
  compilación.
- Se eliminaron las cachés `__pycache__` y `.ruff_cache`.
- Se retiró el directorio vacío `ai/models` junto con su contenedor vacío.
- Se eliminaron 494 líneas de una interfaz anterior que ya no podía ejecutarse:
  el constructor actual delega en `ui.workspace`.
- Se eliminó el antiguo bloque de iconos PNG codificados dentro del fuente
  (12.039 caracteres) y su cargador sin consumidores.
- Se eliminaron importaciones que quedaron sin uso después de esa retirada.

Se conservaron deliberadamente:

- Los binarios y datos de Tesseract, porque sostienen la política de OCR local.
- Los conceptos visuales y documentos de versión, por ser evidencia de diseño y
  procedencia, no temporales de ejecución.
- Los artefactos de catálogo y recuperación definidos por las reglas de
  seguridad del proyecto.

## Evaluación por componente

### Python 3.12: adecuado y recomendable

Python encaja con el perfil real del producto: orquestación de ficheros,
metadatos, SQLite, procesos OCR, lectura de documentos, red opcional y una gran
cantidad de reglas explicables. La mayor parte del trabajo costoso ya ocurre en
bibliotecas nativas o procesos separados (Tesseract y PDFium), por lo que una
reescritura del coordinador en un lenguaje compilado no garantiza una mejora
perceptible.

Además, el activo más costoso de reemplazar no es la sintaxis: son las reglas de
seguridad, recuperación y decisión, junto con sus pruebas. Cambiar de lenguaje
obligaría a volver a demostrar propiedades que hoy ya están expresadas y
probadas.

Riesgos actuales de Python que sí requieren atención:

- módulos demasiado grandes y responsabilidades mezcladas;
- capturas genéricas de excepciones que dificultan distinguir fallos recuperables;
- tipado implícito en contratos entre interfaz, servicios y almacenamiento;
- disciplina de concurrencia necesaria para no tocar Tk desde trabajadores.

Estos problemas se corrigen con arquitectura, tipado gradual, registros y
pruebas; no requieren cambiar de lenguaje.

### Tkinter/Ttk: válido ahora, límite probable a medio plazo

Tkinter es la interfaz estándar de Python para Tcl/Tk y está disponible en
Windows, macOS y sistemas Unix. Su modelo es dirigido por eventos y los
manejadores deben terminar rápido; la propia documentación indica que el trabajo
largo debe dividirse con temporizadores o ejecutarse en otro hilo. La aplicación
ya va en la dirección correcta con colas de eventos, tareas diferidas y trabajo
en segundo plano.

Sus límites relevantes para este producto son:

- las tarjetas y bordes personalizados aumentan el código de renderizado;
- una cuadrícula grande obliga a implementar reutilización y virtualización;
- la accesibilidad de controles dibujados a medida exige trabajo específico;
- DPI, animación, arrastre y componentes complejos requieren más código propio;
- recalcular toda la cuadrícula durante redimensionados bloquea el mismo bucle
  que procesa la interacción.

Conclusión: Tkinter no impide terminar una aplicación sólida, pero ya es la capa
con mayor coste marginal. Debe quedar reemplazable, no expandirse dentro del
núcleo.

### SQLite: elección correcta

SQLite es una base ligera en disco y no necesita un proceso servidor. Es una
elección muy apropiada para un catálogo local de un solo usuario, operaciones
transaccionales, índices de búsqueda y planes recuperables. PostgreSQL u otro
servidor solo tendrían sentido con sincronización multiusuario o servicio remoto,
ninguno de los cuales forma parte del concepto actual.

La dirección recomendada es consolidar SQLite como fuente estructurada, mantener
migraciones explícitas y usar JSON solo para compatibilidad, exportación o
preferencias simples.

### Tesseract, PDFium y Pillow: límites nativos bien elegidos

El proyecto ya evita ejecutar OCR o rasterizado pesado en Python puro. Usar
Tesseract como proceso local y PDFium/Pillow como bibliotecas especializadas
preserva privacidad y rendimiento. Antes de escribir extensiones Rust o C++ se
debe medir un cuello de botella que no pertenezca ya a estas dependencias.

### PyInstaller e Inno Setup: adecuados para Windows

PyInstaller incluye el intérprete y dependencias, por lo que el usuario no debe
instalar Python. La documentación oficial también señala que la salida es
específica del sistema operativo y de la versión de Python: cada plataforma debe
compilarse y probarse en su propio entorno.

El modo `onedir` usado en Windows es coherente: facilita diagnóstico y evita la
extracción temporal y el arranque algo más lento del modo `onefile`. Inno Setup
oculta la carpeta de distribución detrás de un instalador normal. No debe
cambiarse a `onefile` únicamente por apariencia.

## Comparación de alternativas

| Opción | Núcleo y seguridad existentes | Calidad visual potencial | Multiplataforma | Complejidad añadida | Coste de migración | Dictamen |
|---|---:|---:|---:|---:|---:|---|
| Python + Tkinter actual | Muy alta | Media | Alta | Baja | Muy bajo | Mantener ahora |
| Python + PySide6/Qt | Muy alta | Alta | Alta | Media | Medio | Mejor evolución si se activan los criterios |
| C# + WinUI 3 | Muy baja tras reescritura | Muy alta en Windows | Baja | Media | Muy alto | Solo si el producto pasa a ser Windows exclusivo |
| Rust + Tauri + web UI | Baja sin puente Python | Alta | Alta | Alta: Rust, web e IPC | Muy alto | No recomendado para el alcance actual |
| Reescritura completa en Rust/C++ | Muy baja | Depende del toolkit | Media | Muy alta | Extremo | Sin justificación medida |

### Por qué PySide6 es la alternativa preferente

PySide6 son las vinculaciones oficiales de Qt para Python. Permitiría conservar
servicios y pruebas, incorporar un modelo/vista más apropiado para listas de
portadas, mejorar accesibilidad y usar controles con mejor comportamiento nativo.
Qt declara soporte de accesibilidad para MSAA, macOS Accessibility y AT-SPI.

Sus costes son reales: dependencia más grande, empaquetado distinto, curva de
aprendizaje, revisión de licencia LGPLv3/GPLv3 o comercial y reimplementación de
la vista. Por eso debe probarse con un prototipo acotado, no adoptarse por moda.

### Por qué no C#/WinUI ahora

Microsoft recomienda WinUI 3 y Windows App SDK para aplicaciones nuevas de
escritorio Windows; ofrece controles modernos, DPI, accesibilidad y renderizado
de texto excelentes. Sin embargo, WinUI 3 no es multiplataforma y migrar esta
aplicación descartaría el núcleo Python o introduciría un puente entre procesos.
Solo sería racional si se decide formalmente que Windows es el único destino y
la integración nativa pasa a valer más que la continuidad del núcleo.

### Por qué no Tauri ahora

Tauri combina Rust con HTML/CSS/JavaScript en un WebView y comunica ambos lados
por mensajes. Puede producir ejecutables compactos al reutilizar el WebView del
sistema, pero en este proyecto añadiría una frontera IPC, un segundo modelo de
concurrencia y al menos dos lenguajes de producto nuevos. También trasladaría a
la capa web parte de la superficie de seguridad. Es una buena opción para un
equipo web o una estrategia web-escritorio común, no para resolver por sí sola
la velocidad del catálogo actual.

## Criterios objetivos para abandonar Tkinter

Debe abrirse una migración de interfaz si se cumple uno o más de estos criterios
y una optimización razonable no lo corrige:

1. La cuadrícula no mantiene interacción fluida con la biblioteca objetivo aun
   renderizando solo los elementos visibles y reutilizando tarjetas.
2. Buscar o cambiar filtros supera de forma sostenida 100 ms en el tamaño de
   catálogo de referencia.
3. Redimensionar paneles o portadas produce bloqueos visibles pese a aplicar el
   diseño solo al terminar el arrastre y diferir el trabajo pesado.
4. Una auditoría con lector de pantalla y navegación completa por teclado falla
   por limitaciones de los widgets personalizados.
5. El producto necesita múltiples ventanas complejas, arrastrar y soltar rico,
   animación continua, soporte táctil avanzado o integración profunda del SO.
6. Mantener controles Canvas propios consume más esfuerzo que las funciones del
   producto durante dos ciclos consecutivos.

La escala debe medirse con catálogos sintéticos de 1.000, 10.000 y 50.000
elementos. Cambiar de toolkit sin estas mediciones sustituiría evidencia por una
suposición.

## Plan técnico recomendado

### Etapa 1: estabilizar la arquitectura actual

- Seguir extrayendo responsabilidades de `library_core.py` hacia servicios
  pequeños y comprobables.
- Convertir `library_app.py` en coordinador de casos de uso, no almacén de
  componentes visuales.
- Mantener en `ui` toda dependencia de Tk y evitar que `core` importe la vista.
- Definir contratos tipados para catálogo, análisis, planes, progreso,
  cancelación y eventos de interfaz.
- Sustituir capturas genéricas gradualmente, empezando por movimientos,
  reemplazos, cuarentena, recuperación y persistencia.
- Adoptar una línea base de Ruff por directorio; no aplicar correcciones masivas
  sobre los flujos destructivos sin pruebas específicas.

### Etapa 2: medir antes de migrar

- Añadir pruebas de rendimiento reproducibles para carga, búsqueda, filtros,
  desplazamiento y redimensionado.
- Medir tiempo de arranque, memoria, latencia p50/p95 y número de widgets vivos.
- Probar accesibilidad y teclado en el ejecutable instalado, no solo en fuentes.
- Registrar el tamaño de catálogo y hardware usado para que los resultados sean
  comparables.

### Etapa 3: prototipo PySide6 condicionado

Si se activa algún criterio, implementar únicamente la pantalla Biblioteca sobre
una copia de solo lectura del `LibraryViewModel`. Comparar el mismo catálogo y
las mismas métricas. No permitir que el prototipo mueva, renombre o descarte
libros. Migrar después por pantallas, manteniendo el núcleo y las pruebas de
seguridad.

## Fuentes primarias consultadas

- [Tkinter y su modelo de hilos y eventos](https://docs.python.org/3/library/tkinter.html)
- [SQLite desde la biblioteca estándar de Python](https://docs.python.org/3/library/sqlite3.html)
- [Funcionamiento y modos de distribución de PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html)
- [Qt for Python / PySide6](https://doc.qt.io/qtforpython-6/)
- [Despliegue de Qt for Python](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)
- [Accesibilidad de Qt](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QAccessible.html)
- [QListView y arquitectura modelo/vista de Qt](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QListView.html)
- [Windows App SDK](https://learn.microsoft.com/windows/apps/windows-app-sdk/)
- [WinUI 3](https://learn.microsoft.com/windows/apps/winui/)
- [Arquitectura de Tauri](https://v2.tauri.app/concept/architecture/)
- [Modelo de procesos de Tauri](https://v2.tauri.app/concept/process-model/)
