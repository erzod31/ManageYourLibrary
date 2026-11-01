# Android companion

Requested target: an up-to-date Samsung Galaxy S26 Ultra, connected to the
desktop app over Tailscale. Android is a native Java client; catalog, Indra OCR,
identity analysis and recoverable file operations remain on the desktop.
The desktop Tk application is not being replaced or embedded in Android.

The client targets Android 17 / API 37, with Android 8 / API 26 as its minimum.
It uses platform Java APIs, no bundled Python or architecture-specific native
libraries. A physical Samsung device is a separate validation target from an
Android emulator; no universal compatibility or zero-defect claim is made.

Samsung's [official S26 Ultra firmware history](https://doc.samsungmobile.com/SM-S948U1/037368260311/eng.html)
lists Android 17 / One UI 9 for the SM-S948U1, with availability varying by
region/operator. The target is an updated S26 Ultra; that firmware reference
does not establish the exact build on the user's phone. Android 17's
[local-network permission](https://developer.android.com/privacy-and-security/local-network-permission)
is declared and requested explicitly when pairing. No camera, microphone,
location or broad storage permission is required.

Desktop mobile access is off on startup. A visible Android/Tailscale panel
starts/stops access, displays the private HTTPS address, issues a two-minute
single-use pairing code and revokes devices. Only hashes of device tokens are
stored on the PC. Android stores its token using Android Keystore encryption.
The server binds to loopback behind a dedicated, foreground Tailscale Serve
endpoint. Existing endpoints and Funnel must not be altered. The client sends
no credentials to redirects, HTTP endpoints or unrelated public servers.

Books can be browsed, searched, opened, given catalog metadata and transferred with explicit
user selection. Uploads are copies: the phone original is untouched. Indra runs
on the PC. Proposed changes require a preview and explicit confirmation;
ambiguous identities require human review. No permanent-delete endpoint exists.
Plans, undo records, receipts and interrupted jobs must remain recoverable.

Build entry point: `platforms/android/BUILD_ANDROID.ps1`. The Windows installer
must also be updated to include the desktop connection controls and Android
client. Signing keys belong outside Git and must be preserved for updates.

## Primer uso en el S26 Ultra

1. Instala el escritorio **0.5.5** y configura tu carpeta de biblioteca. Abre
   Tailscale en el PC y en el teléfono, conectados a la misma red privada.
2. En el escritorio: **Configuración → Android / Tailscale → Activar acceso**.
   El panel muestra una dirección `https://…ts.net:10443` y un código de ocho
   dígitos. Cerrar ese panel desactiva el acceso; al abrir de nuevo la app
   también empieza desactivado.
3. Instala `ManageYourLibrary-0.5.5.apk` en Android. Puedes transferirlo por
   cable o copiar el enlace privado de descarga desde el panel del PC y abrirlo
   en el teléfono con Tailscale conectado. Android puede pedir que autorices
   la instalación desde la aplicación que abre el APK.
4. En **Conexión**, introduce la dirección exacta y el código del PC; pulsa
   **Vincular de forma privada**. Permite el acceso a dispositivos/red local
   cuando lo solicite Android 17. El permiso se pide al vincular, no al abrir
   por primera vez. Un código caducado o utilizado se renueva desde el PC.
5. Usa Biblioteca, Favoritos, Importar y Actividad. La apariencia Sistema/Claro/
   Oscuro se aplica a todas las páginas. En Conexión puedes ver las licencias
   incluso sin conexión; en el PC puedes desactivar y revocar el acceso.

El PC debe estar encendido y la aplicación abierta con el panel activo.
Tailscale requiere MagicDNS/HTTPS habilitado y permisos de la tailnet para el
puerto 10443. La app no habilita Funnel, no publica la biblioteca en Internet,
no cambia las otras rutas y no modifica las reglas de acceso de Tailscale.
Si ese puerto pertenece a otra aplicación, la activación se detiene y lo
conserva. Referencia: [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).

## Operaciones y límites

- Buscar por título, autor, serie y etiquetas; filtrar formatos y favoritos;
  ver portada, ruta completa y metadatos; editar el catálogo sin renombrar el
  archivo; solicitar el análisis del PC con Indra.
- Abrir un libro descarga una copia verificada y la entrega a un lector Android
  compatible mediante un permiso de lectura. El APK no incluye un lector
  universal de PDF/EPUB/otros formatos. Las copias temporales pueden ser
  eliminadas por Android y no sustituyen una copia de seguridad.
- Elegir un archivo envía una copia a la bandeja del PC. Analizar es una
  previsualización. Revisa título/autor/edición, marca la confirmación, revisa
  el plan y confirma antes de importar. Un destino ocupado detiene el plan.
- La cuarentena también se previsualiza y confirma. Actividad conserva tareas,
  cancelaciones, planes y Deshacer. Un archivo cambiado después de previsualizar
  bloquea la acción. No se elimina definitivamente desde el móvil.
- Transferencias: máximo 512 MiB por archivo; bandeja del PC limitada a unos
  2 GiB más recibos; caché de copias descargadas del móvil hasta 1 GiB. Si falta
  espacio, resuelve los envíos en el PC o borra la caché de la aplicación en los
  ajustes de almacenamiento de Android. No borres los datos de la biblioteca.
- Las tareas largas continúan en el PC al cambiar de pantalla o cerrar Android;
  se consultan/cancelan desde Actividad. Una transferencia interrumpida conserva
  el original: vuelve a seleccionarlo y enviarlo. No hay sincronización completa
  del catálogo sin el PC ni ejecución de Indra en el teléfono.

## Build and signing

Use Windows PowerShell, JDK 21, Android SDK Platform 37 (`android-37.0` or
`android-37`) and Build Tools 36.0.0. Set `JAVA_HOME` and `ANDROID_HOME`, then:

```powershell
.\platforms\android\BUILD_ANDROID.ps1
.\platforms\windows\BUILD_WINDOWS.bat
.\platforms\windows\BUILD_INSTALLER.bat
python tools/package_windows_release.py
```

The APK is `dist/android/ManageYourLibrary-<VERSION>.apk`, signed and verified
with apksigner, and included in the matching Windows payload. There are no
Gradle/Maven runtime dependencies. The Android package is
`com.erzod31.manageyourlibrary`; the QA package is separate and never a release.

The release signing key is outside the repository under the build account's
local application-data folder, `ManageYourLibraryBuild/signing/android/`:
`release.p12` and `password.dpapi`. Preserve the update identity securely.
DPAPI encryption is tied to the Windows account/machine; copying its file alone
does not guarantee recovery on another PC. Never distribute the key/password
with the APK or commit them. CI creates a disposable key for test artifacts;
those artifacts cannot update an APK signed by the maintainer's release key.

`-ForTesting -TestCertificate <public PEM>` builds a debuggable QA APK with an
isolated test CA and the instrumentation under `platforms/android/qa/`.
The production build excludes instrumentation and test certificates, forbids
HTTP, trusts system certificates and disables backups. Tests use a disposable
TLS fixture (`tools/android_qa_server.py`) and their own Android emulator.
`tools/validate_mobile_tailscale.py` separately checks a temporary authenticated
HTTPS endpoint and asserts the pre-existing Serve configuration is unchanged.
`--mobile-self-test <report.json>` exercises the bundled desktop API and safe
operations in a temporary empty profile without changing Tailscale.

Current artifact results and limitations are recorded in
[the 0.5.5 verification report](windows_0.5.5_checksums.md). Android 17 emulator
validation is separate from a physical S26 Ultra, real Samsung firmware,
TalkBack, and a phone-to-PC mobile-data connection. Those must not be claimed
as tested without recording an actual device run.

## Actualizar desde Android

En Conexión → Actualizar esta aplicación: Buscar, descargar y verificar el APK del PC, e Instalar tras confirmar. Android conserva su autorización de origen y su instalador. El certificado debe coincidir con el de la app instalada. No se actualiza la app al iniciar ni al volver de Ajustes. Las ediciones antiguas necesitan una primera instalación manual; consulta [DG-0020](IN_APP_UPDATES.md).
