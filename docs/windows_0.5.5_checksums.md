# Candidatos 0.5.5 · DG-0020

Windows 0.5.5 checksums · ejecutable: `dist/windows/ManageYourLibrary/ManageYourLibrary.exe`.
SHA256: `97C9F02012FF7A722088D8BB231F296FC4088AFB541123F3A67DF69C422FD40D`

Este informe conserva los resultados del 28 de octubre de 2026. DG-0035 añade
la referencia explícita al ejecutable y su hash; no presenta esas pruebas como
una nueva ejecución ni reconstruye los paquetes por este cambio documental.

Base Git: `0480074649b2a8c638ca9175dcfea9708bed0a10` con cambios locales preservados.
Huella de las 271 entradas de código/configuración: `8C9978313220E204366AB73EC8E752DCE66FFF73313E57A5F612F5BBD0E61007`.

Estos paquetes son candidatos locales. No se ha publicado una versión ni ejecutado el instalador/actualizador/desinstalador de Windows.

| Paquete | Bytes | SHA-256 |
| --- | ---: | --- |
| ManageYourLibrary-0.5.5-Setup-x64.exe | 126199860 | `E893770AD2B149581132B25C0D828D0CD4BA1A563D7B57C1FD2C040A6A7F5660` |
| ManageYourLibrary-0.5.5-Windows-x64-portable.zip | 155675794 | `9CED529D360B7B0713EA8717DACBFBBD49073AA208E8ADF1B6F1310EEA984345` |
| ManageYourLibrary-0.5.5.apk | 70301 | `8A77C145630F7B41141486FE1FB5FBBB3A34A20506DF5E6014E87EEC6DC5E054` |
| ManageYourLibrary-0.5.5-Linux-x64.tar.gz | 212205828 | `B36D6B4EA21F0010401C25C455D61194BD814A5A1DF240F845DADD6863A51A14` |

- Windows: 452 pruebas, 2 omisiones POSIX; compilación y cinco comprobaciones del ejecutable congelado.
- Instalador: extracción independiente, 1206 archivos idénticos; cinco comprobaciones desde la extracción con perfil temporal y PATH de Windows. Firma Authenticode: NotSigned.
- Linux: 452 pruebas, 1 omisión Windows; ELF real probado en Ubuntu22.04 aislado, OCR, primer inicio, API móvil y actualizador con lanzador falso. Archivo final: 423 archivos, 36 enlaces internos verificados.
- Android: nueve pruebas nativas del actualizador con instalador falso, nueve del cliente y dos de permisos en API37; APK de producción verificado con apksigner v2/v3, sin QA ni bibliotecas nativas.
- La clave Android existente se conserva. No se actualizó ningún teléfono ni instalación del usuario.
- Seis comprobaciones de controles Tk reales con canal simulado; no equivalen a una actualización instalada.
- macOS arm64/x64: identidad original comprobada en ambos ZIP publicados; faltan compilación actual y comprobación nativa de firma/Gatekeeper/actualización.
- Pendientes: S26 Ultra físico, ruta real teléfono-PC Tailscale, actualización real autorizada y validación macOS.
- El canal público observado ofrece 0.5.3; no se simula disponibilidad de 0.5.5. Las versiones antiguas necesitan una primera transición manual.

Detalles, procedencia y límites: [in-app-updates-DG-0020.json](in-app-updates-DG-0020.json).
