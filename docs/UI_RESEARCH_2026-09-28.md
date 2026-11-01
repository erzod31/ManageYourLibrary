# Investigación de interfaz — Manage Your Library

Fecha: 28 de septiembre de 2026

## Resumen ejecutivo

La aplicación ya tiene una base visual coherente —tema claro/oscuro, tarjetas,
progreso, estado y acciones seguras—, pero la ventana principal funciona como un
panel de operaciones. El contenido que el usuario quiere gestionar, su
biblioteca, no ocupa el centro de la experiencia.

La dirección recomendada combina cuatro patrones:

1. Un armazón de navegación lateral estable, como la propuesta A.
2. Dos vistas intercambiables de la biblioteca: portadas para explorar y tabla
   para trabajar en volumen, como las propuestas B y C.
3. Un panel de detalles que permita consultar y editar sin abrir ventanas
   modales.
4. Un flujo guiado para importar, revisar duplicados y confirmar cambios, como
   la propuesta D.

No conviene escoger entre “bonito” y “potente”: A debe ser la estructura general,
B y C deben ser modos de la misma biblioteca, y D debe reservarse para las
operaciones que pueden modificar archivos.

## Diagnóstico de la interfaz actual

La ventana actual está diseñada como una página vertical desplazable de
1080 × 840 píxeles. Presenta, en orden, la ruta activa, un conjunto grande de
acciones, el estado de la tarea y un registro técnico. Los flujos de metadatos,
duplicados, IA y configuración aparecen en ventanas secundarias.

Fortalezas actuales:

- La acción principal, el progreso y la cancelación son visibles.
- El estado de la biblioteca y el registro transmiten control.
- Los temas claro y oscuro ya comparten una paleta consistente.
- Las operaciones delicadas tienen confirmación, recuperación y deshacer en la
  lógica del producto.

Problemas principales:

- La biblioteca no se puede recorrer visualmente desde la pantalla inicial.
- Hay demasiadas acciones con peso parecido y poca separación entre destinos,
  tareas y opciones avanzadas.
- El registro ocupa mucho espacio permanente aunque normalmente solo se necesita
  al diagnosticar un problema.
- La ruta del sistema de archivos se presenta como elemento protagonista, cuando
  debería ser información contextual o de configuración.
- Las ventanas modales fragmentan la tarea y dificultan comparar un libro con su
  contexto.
- El diseño se adapta reduciendo y desplazando el contenido, pero no cambia su
  jerarquía para ventanas estrechas.

## Evidencia de diseño utilizada

Microsoft recomienda el patrón de lista y detalle cuando hay que localizar y
priorizar una colección grande, aplicar operaciones individuales o por lotes y
consultar o editar el elemento seleccionado. También recomienda mostrar ambos
paneles a partir de 641 píxeles y apilarlos en ventanas más estrechas:
https://learn.microsoft.com/en-us/windows/apps/develop/ui/controls/list-details

Para aplicaciones con varias áreas estables, `NavigationView` ofrece navegación
lateral adaptable. Microsoft aconseja navegación superior con cinco destinos o
menos y lateral cuando hay entre cinco y diez; también recomienda mantener la
jerarquía poco profunda:
https://learn.microsoft.com/en-us/windows/apps/design/controls/navigationview

La guía de aplicaciones de productividad de Windows aconseja adaptar la
jerarquía en vez de encoger todos los controles, conservar foco visible, no
expresar estado solo mediante color y mantener la operación completa accesible
por teclado:
https://learn.microsoft.com/en-us/windows/apps/get-started/line-of-business/design-for-lob

Calibre demuestra que una biblioteca madura necesita más de una representación:
lista, cuadrícula de portadas, estantería y panel de detalles. Su documentación
también muestra que las acciones frecuentes deben estar accesibles sin ocultar
los detalles del libro:
https://manual.calibre-ebook.com/gui.html

Zotero aporta un patrón muy eficaz para colecciones extensas: colecciones y
filtros a la izquierda, elementos en el centro y metadatos a la derecha. Las
colecciones se comportan como listas, no como copias físicas, y las búsquedas
guardadas se actualizan automáticamente:
https://www.zotero.org/support/collections_and_tags

La búsqueda rápida de Zotero diferencia título/autor, todos los campos y texto
completo. Para Manage Your Library conviene presentar esos alcances como una
opción clara del buscador, sin obligar a aprender una sintaxis:
https://www.zotero.org/support/searching

WCAG 2.2 fija un objetivo mínimo de 24 × 24 píxeles CSS para controles de
puntero, con excepciones, y exige que el foco visible tenga área suficiente y
contraste. En una aplicación de escritorio se recomienda superar ese mínimo y
usar controles principales de 40–44 píxeles:
https://www.w3.org/TR/WCAG/

## Arquitectura recomendada

### Navegación

- **Biblioteca**: destino inicial; cuadrícula o tabla con panel de detalles.
- **Importar**: flujo guiado y recuperable.
- **Revisiones**: duplicados, metadatos dudosos, libros sin portada y errores.
- **Actividad**: trabajos actuales, historial, planes interrumpidos y registro
  técnico expandible.
- **Configuración**: fijada al pie de la barra lateral.

`Inicio` solo aporta valor si resume asuntos pendientes y actividad reciente. Si
no puede ofrecer información accionable, debe omitirse y abrir directamente la
biblioteca.

### Biblioteca

- Buscador global siempre visible con `Ctrl+K` y `Ctrl+F`.
- Filtros rápidos como formato, idioma, estado y calidad de metadatos.
- Alternancia entre cuadrícula de portadas y tabla, conservando selección,
  filtros y posición.
- Panel derecho de detalles editable, ocultable y redimensionable.
- Acciones por lote únicamente después de seleccionar elementos.
- Menú contextual para acciones menos frecuentes; no duplicarlas por toda la
  interfaz.

### Operaciones y seguridad

- Barra inferior de actividad compacta y persistente durante tareas largas.
- Vista previa antes de mover, sustituir o descartar archivos.
- Diferenciar visual y verbalmente “duplicado exacto” de “posible coincidencia”.
- Mostrar cuántos cambios se aplicarán y recordar que existe la opción de
  deshacer.
- Mantener Cancelar junto al progreso de la operación, no junto a acciones de
  navegación.
- Convertir el registro técnico en un panel expandible dentro de Actividad.

### Accesibilidad y densidad

- Objetivos principales de 40–44 píxeles; nunca menos de 24 × 24.
- Indicador de foco de al menos 2 píxeles y contraste mínimo 3:1 respecto al
  estado sin foco.
- Etiqueta textual o icono adicional para cada estado; el color no basta.
- Orden de tabulación: navegación, búsqueda, comandos, contenido, detalles.
- Escalado de texto probado al 125 %, 150 % y 200 %.
- Diseño adaptable: a menos de 760 píxeles, ocultar el inspector tras la
  selección y convertir la barra lateral en compacta.

## Las cuatro propuestas

### A — Centro de biblioteca

La opción más equilibrada y fácil de aprender. Presenta métricas, asuntos
pendientes y libros recientes sin perder una navegación estable. Es la mejor
base estructural, pero no debe convertirse en un panel de estadísticas sin
acceso directo al catálogo.

### B — Galería editorial

La mejor opción para explorar colecciones personales y reconocer libros por la
portada. El inspector lateral evita ventanas modales. Debe incluir un modo tabla
para usuarios con miles de documentos o portadas ausentes.

### C — Catálogo profesional

La opción más eficiente para bibliotecas grandes, edición masiva y trabajo con
teclado. La densidad exige buenos valores predeterminados, paneles
redimensionables y un modo claro equivalente. No debe ser la única vista para
usuarios ocasionales.

### D — Flujo guiado y seguro

La mejor solución para importar y resolver duplicados. Hace visibles las etapas,
las consecuencias y la posibilidad de deshacer. No sustituye a la biblioteca;
es un espacio de trabajo temporal para operaciones de riesgo.

## Recomendación final

Adoptar **A como armazón**, ofrecer **B y C como vistas de Biblioteca** y usar
**D para Importar y Revisiones**. Esta combinación aprovecha la seguridad que ya
existe en el motor, reduce la dependencia de ventanas modales y ofrece una ruta
clara tanto para usuarios ocasionales como para bibliotecas grandes.

Orden de implementación propuesto:

1. Crear el armazón lateral y trasladar configuración/actividad.
2. Construir el modelo de vista Biblioteca con cuadrícula, tabla e inspector.
3. Integrar búsqueda, filtros y selecciones por lote.
4. Migrar importación y duplicados al flujo guiado.
5. Completar navegación por teclado, escalado, lector de pantalla y contraste.
