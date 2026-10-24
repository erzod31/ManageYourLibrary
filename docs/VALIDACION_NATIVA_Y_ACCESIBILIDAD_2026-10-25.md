# Validación nativa y accesibilidad — 2026-10-25

Continuación del informe del 24 de octubre. La autorización nueva permite subir
la rama `codex/audit-optimizations` para pruebas, **no publicar una versión**.
No se han creado tags, fusionado `main` ni modificado versiones publicadas.
El repositorio privado y el perfil/biblioteca del usuario quedan fuera del trabajo.

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
nativo; la repetición visual quedó detenida al bloquearse Windows. La habilidad
`computer-use` exige detener la automatización cuando el escritorio está bloqueado.
No se ha intentado eludir el bloqueo. Para cerrar esa comprobación se necesita
desbloquear el equipo y volver a comprobar el árbol externo y las acciones.

Tk 8.6 continúa funcionando como alternativa de ejecución, pero se declara sin
backend nativo de accesibilidad. No se presenta como equivalente a Tk 9.1.

## Cómo reproducir sin tocar la instalación habitual

En CI, `.github/workflows/native-release.yml` resuelve ruedas nativas, construye
el runtime GUI fijado, ejecuta el probe y usa los scripts de plataforma existentes.
Los pushes de la rama de pruebas no pueden activar el trabajo de publicación.
Las ejecuciones de push obsoletas pueden cancelarse al llegar otra revisión.

En Windows se requiere Python 3.12 y un compilador MSVC x64 de Build Tools:

```powershell
py -3.12 -m venv .venv-tk91
.venv-tk91/Scripts/python -m pip install --require-hashes -r requirements.lock
.venv-tk91/Scripts/python -B tools/build_accessible_tk.py --output dist/native-gui-windows
.venv-tk91/Scripts/python -B tools/verify_accessibility.py --output dist/accessibility-self-test.json
$env:MANAGE_YOUR_LIBRARY_PYTHON = "$PWD/.venv-tk91/Scripts/python.exe"
$env:MANAGE_YOUR_LIBRARY_DIST_DIR = "$PWD/dist/windows-tk91"
./platforms/windows/BUILD_WINDOWS.bat
```

Los destinos deben ser nuevos. La activación `.pth` se escribe únicamente en ese
entorno virtual. Los libros, el catálogo y la instalación habitual no son entradas
de estas pruebas. No se distribuyen los binarios generados dentro del historial Git.

## Licencias y publicación

La [revisión individual del OCR Windows](LICENCIAS_OCR_2026-10-25.md) cubre 57
binarios y sigue con redistribución pendiente. Los componentes macOS/Linux tienen
sus propios manifiestos; el resultado Windows no los autoriza automáticamente.
Un resultado de compilación, OCR o accesibilidad correcto no sustituye las
obligaciones de licencias, la firma de distribución ni una auditoría de seguridad.

El siguiente cierre requiere interoperabilidad con lectores reales, completar
las fuentes/avisos del OCR y revisar seguridad nativa. Nada de lo anterior autoriza
publicar una versión nueva sin la decisión correspondiente del propietario.
