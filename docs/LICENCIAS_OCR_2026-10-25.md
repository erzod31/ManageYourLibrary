# Revisión de procedencia y licencias del OCR Windows

Fecha: 2026-10-25. Alcance: las 56 DLL y el ejecutable del runtime heredado,
no solo Tesseract. Revisión técnica de evidencias y obligaciones, no un dictamen
jurídico ni una auditoría de vulnerabilidades.

## Conclusión

La revisión inicial cubre individualmente los 57 binarios, pero **el conjunto
no está aprobado para una nueva redistribución pública**. No se ha cambiado la
licencia MIT del código propio, sustituido/eliminado DLL ni publicado una versión.

- Los 57 SHA-256 coinciden con el instalador oficial de Tesseract 5.5.0.20241111.
  Sus seis modelos también coinciden con repositorios oficiales.
- Se contrastaron 44 familias con recetas históricas de MSYS2, fijadas en el commit
  `d69cf6a6c704ce9863d193ec45cbf0b73197d5d5` (2024-11-11).
- 21 binarios coinciden además byte por byte con paquetes históricos descargables
  de MSYS2. Para los otros 36, la versión de receta es **candidata**, no un recibo
  probado del paquete. Un 404 no significa que su licencia sea desconocida ni
  que el archivo sea ilegítimo; impide esa comprobación adicional.
- Se recuperaron 21 archivos de avisos de paquetes coincidentes, sin alterar sus
  bytes. Se incorporan bajo `tesseract/licenses/reviewed-package-notices` y al
  empaquetado Windows existente. No se ejecutaron el instalador ni los binarios
  descargados para la comparación. No se verificaron firmas PGP.
- Todos los registros conservan `redistribution_review: not_complete`. El
  empaquetador Windows sigue bloqueando una distribución normal. Una compilación
  de desarrollo no es una autorización de redistribución.

[Inventario SHA-256 del instalador](validation_data_2026-10-24/windows-ocr-provenance.json),
[revisión y recibos por binario](validation_data_2026-10-25/windows-ocr-license-review.json),
[catálogo de licencias y obligaciones](../tools/ocr_license_catalog.json).

## Hallazgos importantes

1. **JBIG-KIT es GPL, no BSD ni Apache.** El SHA-256 de `libjbig-0.dll` coincide
   con el paquete MSYS2 2.1-5. El encabezado de `libjbig/jbig.c` del
   [fuente oficial 2.1](https://www.cl.cam.ac.uk/~mgk25/download/jbigkit-2.1.tar.gz)
   concede GPLv2 o posterior. El import PE prueba que `libtiff-6.dll` lo enlaza.
   El [autor](https://www.cl.cam.ac.uk/~mgk25/jbigkit/) describe la licencia GPL
   y la posibilidad de negociar otra licencia; no se ha solicitado ni adquirido.
   Conservar solo la licencia Apache de Tesseract no resuelve esa combinación.
   Hay que documentar una vía de licencias compatible para el conjunto OCR y
   entregar su fuente correspondiente, o reconstruir TIFF/OCR sin ese códec.
2. **LGPL no significa prohibido ni significa sin obligaciones.** GLib/GIO,
   Pango, Cairo, FriBidi, libdatrie, libthai, libiconv, libintl, libidn2,
   libunistring y Graphite requieren su vía de copyleft débil o una alternativa
   válida. Deben revisarse fuentes correspondientes, parches, avisos, reemplazo/
   re-enlace de biblioteca y derechos del destinatario. La app comunica con
   Tesseract por proceso separado; no se concluye automáticamente que la GUI
   Python deba cambiar de MIT a GPL.
3. **Paquete completo y DLL no son lo mismo.** `libiconv-2.dll` y
   `libintl-8.dll` tienen la vía LGPL de biblioteca aunque sus herramientas
   tienen GPL. `liblz4.dll` usa BSD y `liblzma-5.dll` 5.6.3 usa 0BSD.
   No se les asigna GPL solo porque el paquete incluya herramientas GPL.
   [Licencias de XZ 5.6.3](https://github.com/tukaani-project/xz/blob/v5.6.3/COPYING).
4. **Las alternativas tienen que elegirse y cumplirse.** FreeType ofrece FTL/GPL;
   Graphite 1.3.14 LGPL/MPL/GPL, **no MIT**; Cairo LGPL/MPL; Zstd BSD/GPL.
   La [excepción de GCC](https://github.com/gcc-mirror/gcc/blob/releases/gcc-14.2.0/COPYING.RUNTIME)
   permite combinaciones que satisfagan sus condiciones; no convierte sus
   runtime en MIT ni elimina las obligaciones del propio runtime.
5. **Hay avisos permisivos específicos.** ICU 75.1 incorpora Unicode License V3
   y avisos de terceros: no basta una etiqueta «ICU». JPEG/Turbo necesita los
   textos IJG/BSD/zlib aplicables; FreeType su reconocimiento FTL; libpng, curl,
   Fontconfig y TIFF sus textos propios. libpsl requiere examinar además los
   datos Public Suffix List y su posible MPL-2.0: MIT del código no cubre todos
   los datos. Pango conserva encabezados Library GPLv2-o-posterior y debe
   documentarse la vía LGPL elegida para los componentes concretos del build.
6. **Simplificación posible, no eliminación automática.** El cierre de
   importaciones PE desde `tesseract.exe` alcanza 35 de los 57 binarios.
   Los otros 22 pertenecen a familias como Pango/Cairo/GLib/ICU. Esto no descarta
   cargas dinámicas ni funciones opcionales. No se borraron; reducir el paquete
   exige registrar cargas y probar los idiomas, formatos y salidas utilizados.
   JBIG sí está en la cadena alcanzable y no desaparece quitando esos candidatos.

## Resultado individual

«Paquete exacto» significa coincidencia SHA-256 con la versión indicada.
«Receta» significa versión candidata de la receta histórica; la procedencia del
instalador sí es exacta en todas las filas. La licencia recoge la vía/familia
revisada y sus avisos compuestos, no certifica el cumplimiento de sus condiciones.
El catálogo enlazado contiene las obligaciones y reservas específicas.

| Archivo | Licencia/vía revisada (fuente) | Evidencia MSYS2 |
| --- | --- | --- |
| `libLerc.dll` | [Apache-2.0](https://github.com/Esri/lerc/blob/v4.0.0/LICENSE) | Paquete exacto 4.0.0-1 |
| `libarchive-13.dll` | [BSD-2-Clause AND BSD-3-Clause AND LicenseRef-libarchive-contributors](https://github.com/libarchive/libarchive/blob/v3.7.7/COPYING) | Paquete exacto 3.7.7-1 |
| `libb2-1.dll` | [CC0-1.0](https://github.com/BLAKE2/libb2/blob/v0.98.1/COPYING) | Paquete exacto 0.98.1-2 |
| `libbrotlicommon.dll` | [MIT](https://github.com/google/brotli/blob/v1.1.0/LICENSE) | Receta 1.1.0-3 |
| `libbrotlidec.dll` | [MIT](https://github.com/google/brotli/blob/v1.1.0/LICENSE) | Receta 1.1.0-3 |
| `libbz2-1.dll` | [bzip2-1.0.6](https://sourceware.org/git/?p=bzip2.git;a=blob;f=LICENSE;hb=bzip2-1.0.8) | Paquete exacto 1.0.8-3 |
| `libcairo-2.dll` | [LGPL-2.1-or-later OR MPL-1.1](https://gitlab.freedesktop.org/cairo/cairo/-/blob/1.18.2/COPYING) | Receta 1.18.2-1 |
| `libcrypto-3-x64.dll` | [Apache-2.0](https://github.com/openssl/openssl/blob/openssl-3.4.0/LICENSE.txt) | Receta 3.4.0-1 |
| `libcurl-4.dll` | [curl](https://github.com/curl/curl/blob/curl-8_11_0/COPYING) | Receta 8.11.0-2 |
| `libdatrie-1.dll` | [LGPL-2.1-or-later](https://github.com/tlwg/libdatrie/blob/v0.2.13/COPYING) | Paquete exacto 0.2.13-3 |
| `libdeflate.dll` | [MIT](https://github.com/ebiggers/libdeflate/blob/v1.22/COPYING) | Receta 1.22-1 |
| `libexpat-1.dll` | [MIT](https://github.com/libexpat/libexpat/blob/R_2_6_4/expat/COPYING) | Paquete exacto 2.6.4-1 |
| `libffi-8.dll` | [MIT](https://github.com/libffi/libffi/blob/v3.4.6/LICENSE) | Paquete exacto 3.4.6-1 |
| `libfontconfig-1.dll` | [LicenseRef-Fontconfig](https://gitlab.freedesktop.org/fontconfig/fontconfig/-/blob/2.15.0/COPYING) | Receta 2.15.0-2 |
| `libfreetype-6.dll` | [FTL OR GPL-2.0-or-later](https://gitlab.freedesktop.org/freetype/freetype/-/blob/VER-2-13-3/docs/FTL.TXT) | Paquete exacto 2.13.3-1 |
| `libfribidi-0.dll` | [LGPL-2.1-or-later](https://github.com/fribidi/fribidi/blob/v1.0.16/COPYING) | Paquete exacto 1.0.16-1 |
| `libgcc_s_seh-1.dll` | [GPL-3.0-or-later WITH GCC-exception-3.1](https://github.com/gcc-mirror/gcc/blob/releases/gcc-14.2.0/COPYING.RUNTIME) | Paquete exacto 14.2.0-2 |
| `libgif-7.dll` | [MIT](https://sourceforge.net/p/giflib/code/ci/5.2.2/tree/COPYING) | Paquete exacto 5.2.2-1 |
| `libgio-2.0-0.dll` | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/glib/-/blob/2.82.2/LICENSES/LGPL-2.1-or-later.txt) | Receta 2.82.2-1 |
| `libglib-2.0-0.dll` | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/glib/-/blob/2.82.2/LICENSES/LGPL-2.1-or-later.txt) | Receta 2.82.2-1 |
| `libgmodule-2.0-0.dll` | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/glib/-/blob/2.82.2/LICENSES/LGPL-2.1-or-later.txt) | Receta 2.82.2-1 |
| `libgobject-2.0-0.dll` | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/glib/-/blob/2.82.2/LICENSES/LGPL-2.1-or-later.txt) | Receta 2.82.2-1 |
| `libgraphite2.dll` | [LGPL-2.1-or-later OR MPL-1.1 OR GPL-2.0-or-later](https://github.com/silnrsi/graphite/blob/1.3.14/COPYING) | Paquete exacto 1.3.14-3 |
| `libharfbuzz-0.dll` | [MIT](https://github.com/harfbuzz/harfbuzz/blob/10.1.0/COPYING) | Receta 10.1.0-1 |
| `libiconv-2.dll` | [LGPL-2.1-or-later](https://www.gnu.org/software/libiconv/) | Receta 1.17-4 |
| `libicudt75.dll` | [Unicode-3.0 AND ICU AND LicenseRef-ICU-third-party](https://github.com/unicode-org/icu/blob/release-75-1/LICENSE) | Receta 75.1-2 |
| `libicuin75.dll` | [Unicode-3.0 AND ICU AND LicenseRef-ICU-third-party](https://github.com/unicode-org/icu/blob/release-75-1/LICENSE) | Receta 75.1-2 |
| `libicuuc75.dll` | [Unicode-3.0 AND ICU AND LicenseRef-ICU-third-party](https://github.com/unicode-org/icu/blob/release-75-1/LICENSE) | Receta 75.1-2 |
| `libidn2-0.dll` | [(LGPL-3.0-or-later OR GPL-2.0-or-later) AND LicenseRef-Libidn2-Unicode](https://github.com/libidn/libidn2/blob/v2.3.7/COPYING) | Paquete exacto 2.3.7-2 |
| `libintl-8.dll` | [LGPL-2.1-or-later](https://www.gnu.org/software/gettext/manual/html_node/Licenses.html) | Receta 0.22.5-2 |
| `libjbig-0.dll` | [GPL-2.0-or-later](https://www.cl.cam.ac.uk/~mgk25/jbigkit/) | Paquete exacto 2.1-5 |
| `libjpeg-8.dll` | [IJG AND BSD-3-Clause AND Zlib](https://github.com/libjpeg-turbo/libjpeg-turbo/blob/3.0.4/LICENSE.md) | Receta 3.0.4-2 |
| `libleptonica-6.dll` | [BSD-2-Clause](https://github.com/DanBloomberg/leptonica/blob/1.85.0/leptonica-license.txt) | Paquete exacto 1.85.0-1 |
| `liblz4.dll` | [BSD-2-Clause](https://github.com/lz4/lz4/blob/v1.10.0/lib/LICENSE) | Paquete exacto 1.10.0-1 |
| `liblzma-5.dll` | [0BSD](https://github.com/tukaani-project/xz/blob/v5.6.3/COPYING) | Receta 5.6.3-2 |
| `libopenjp2-7.dll` | [BSD-2-Clause](https://github.com/uclouvain/openjpeg/blob/v2.5.2/LICENSE) | Receta 2.5.2-1 |
| `libpango-1.0-0.dll` | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/pango/-/blob/1.54.0/COPYING) | Receta 1.54.0-1 |
| `libpangocairo-1.0-0.dll` | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/pango/-/blob/1.54.0/COPYING) | Receta 1.54.0-1 |
| `libpangoft2-1.0-0.dll` | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/pango/-/blob/1.54.0/COPYING) | Receta 1.54.0-1 |
| `libpangowin32-1.0-0.dll` | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/pango/-/blob/1.54.0/COPYING) | Receta 1.54.0-1 |
| `libpcre2-8-0.dll` | [BSD-3-Clause](https://github.com/PCRE2Project/pcre2/blob/pcre2-10.44/LICENCE) | Receta 10.44-1 |
| `libpixman-1-0.dll` | [MIT](https://gitlab.freedesktop.org/pixman/pixman/-/blob/pixman-0.44.0/COPYING) | Receta 0.44.0-1 |
| `libpng16-16.dll` | [libpng-2.0](https://github.com/pnggroup/libpng/blob/v1.6.44/LICENSE) | Receta 1.6.44-1 |
| `libpsl-5.dll` | [MIT AND MPL-2.0](https://github.com/rockdaboot/libpsl/blob/0.21.5/COPYING) | Receta 0.21.5-2 |
| `libsharpyuv-0.dll` | [BSD-3-Clause](https://github.com/webmproject/libwebp/blob/v1.4.0/COPYING) | Receta 1.4.0-1 |
| `libssh2-1.dll` | [BSD-3-Clause](https://github.com/libssh2/libssh2/blob/libssh2-1.11.0/COPYING) | Receta 1.11.0-2 |
| `libstdc++-6.dll` | [GPL-3.0-or-later WITH GCC-exception-3.1](https://github.com/gcc-mirror/gcc/blob/releases/gcc-14.2.0/COPYING.RUNTIME) | Paquete exacto 14.2.0-2 |
| `libtesseract-5.dll` | [Apache-2.0](https://github.com/tesseract-ocr/tesseract/blob/5.5.0/LICENSE) | Receta 5.5.0-1 |
| `libthai-0.dll` | [LGPL-2.1-or-later](https://github.com/tlwg/libthai/blob/v0.1.29/COPYING) | Paquete exacto 0.1.29-3 |
| `libtiff-6.dll` | [libtiff](https://gitlab.com/libtiff/libtiff/-/blob/v4.7.0/LICENSE.md) | Paquete exacto 4.7.0-1 |
| `libunistring-5.dll` | [LGPL-3.0-or-later OR GPL-2.0-or-later](https://www.gnu.org/software/libunistring/) | Receta 1.2-1 |
| `libwebp-7.dll` | [BSD-3-Clause](https://github.com/webmproject/libwebp/blob/v1.4.0/COPYING) | Receta 1.4.0-1 |
| `libwebpmux-3.dll` | [BSD-3-Clause](https://github.com/webmproject/libwebp/blob/v1.4.0/COPYING) | Receta 1.4.0-1 |
| `libwinpthread-1.dll` | [MIT AND BSD-3-Clause-Clear](https://github.com/mingw-w64/mingw-w64/blob/0d42217123d3aec0341b79f6d959c76e09648a1e/mingw-w64-libraries/winpthreads/COPYING) | Receta 12.0.0.r369.g0d4221712-1 |
| `libzstd.dll` | [BSD-3-Clause OR GPL-2.0-or-later](https://github.com/facebook/zstd/blob/v1.5.6/LICENSE) | Paquete exacto 1.5.6-2 |
| `tesseract.exe` | [Apache-2.0](https://github.com/tesseract-ocr/tesseract/blob/5.5.0/LICENSE) | Receta 5.5.0-1 |
| `zlib1.dll` | [Zlib](https://github.com/madler/zlib/blob/v1.3.1/LICENSE) | Paquete exacto 1.3.1-1 |

## Qué falta para aprobar el paquete

- Completar recibos de compilación de los 36 binarios sin coincidencia de paquete
  y fijar sus versiones reales, sin adoptar ciegamente la receta histórica.
- Reunir avisos y atribuciones completos, incluyendo código enlazado estáticamente
  y datos integrados. Que un paquete no incluya avisos no libera de condiciones.
- Resolver la combinación GPL de JBIG y reunir fuente correspondiente, parches y
  scripts de construcción de los componentes copyleft. Una página de inicio no
  es suficiente. Definir una entrega de fuentes válida para las licencias y la
  forma concreta de distribución. No emitir ofertas escritas de larga duración
  sin poder cumplirlas.
- Preferencia técnica: construir un runtime OCR mínimo desde fuentes fijadas,
  sin utilidades gráficas innecesarias ni JBIG si la app no lo necesita, con SBOM,
  avisos y archivo de fuentes asociados al build. No se ha sustituido el runtime
  de producción por una compilación no probada.
- Pasar OCR, formatos y recuperación y revisar vulnerabilidades nativas por
  separado. Licencias correctas y análisis de dependencias Python no acreditan
  la seguridad de las DLL.

## Reproducción y límites

`tools/audit_windows_ocr.py` compara el instalador extraído sin ejecutarlo.
`tools/collect_ocr_license_evidence.py` descarga recetas/paquetes como datos,
compara SHA-256 y lee los avisos del tar sin instalarlo ni ejecutar recetas.
`tools/write_ocr_license_review.py` verifica los recibos antes de exportarlos,
rechaza sobrescribir informes o alterar avisos existentes y nunca deduce un
estado de autorización a partir de una coincidencia.

Los hashes de JSON usan la representación canónica declarada para evitar falsos
cambios por finales de línea Windows/Unix. Los hashes de DLL, paquetes y avisos
usan bytes exactos. Las pruebas comprueban cobertura única de los 57 binarios,
coherencia de hashes, avisos verbatim y que obligaciones pendientes no aparezcan
como aprobadas. Los avisos legales conservan las atribuciones requeridas a sus
autores; no son datos privados del propietario de esta aplicación.

