# Primer uso: Windows, Mac y Linux

Para Mac (Apple Silicon o Intel) y Linux x64, descarga el paquete correspondiente
del [suplemento nativo](https://github.com/erzod31/ManageYourLibrary/releases/tag/v0.5.3-native.2)
y sigue las [instrucciones nativas](NATIVE_FIRST_USE.md). Incluyen Python y OCR.
En Mac extrae el ZIP y copia la app a Aplicaciones; no está notarizada por Apple.
En Linux extrae todo el tar.gz y ejecuta `ManageYourLibrary/ManageYourLibrary`
desde un escritorio gráfico compatible. Las pruebas se hicieron en macOS 15 y
Ubuntu 22.04 x64; no certifican otros sistemas. Después elige la carpeta e importa
como se describe abajo.

## Windows x64

1. Descarga el instalador de la versión publicada y ejecútalo. No necesitas
   Python, una cuenta de la app ni claves API. El OCR ya está incluido.
2. Si eliges la edición portátil, extrae todo el ZIP. Abre `ManageYourLibrary.exe`
   y conserva `_internal`; no ejecutes solo el EXE ni desde el ZIP.
3. Pulsa **Elegir carpeta de biblioteca** y selecciona una carpeta propia con
   permisos de escritura. Espera al índice si ya contiene libros.
4. Usa **Importar** para añadir libros. Confirmar puede mover y renombrar los
   originales: haz una copia de seguridad y prueba con copias de pocos archivos.
5. Resuelve los casos dudosos en **Revisiones**. **Abrir** usa el lector
   predeterminado de Windows: debes tener un lector asociado a PDF o EPUB.

Internet permite consultar metadatos y portadas web; el modo sin conexión trabaja
localmente. El OCR no envía documentos. La IA local es opcional, desactivada por
defecto y requiere un motor y modelo aparte. DOC, DjVu y algunos CBR pueden
necesitar herramientas externas.

Los perfiles nuevos empiezan vacíos y siguen idioma y apariencia del sistema
cuando están disponibles. La configuración se guarda en
`%APPDATA%\ManageYourLibrary`. El instalador y el portátil bajo la misma cuenta
conservan ese perfil; no son un restablecimiento de fábrica.

Los ejecutables no tienen firma digital. Consulta las pruebas y limitaciones
reales de la versión. Los checks automáticos no garantizan por sí solos la
instalación o actualización en todos los equipos.
