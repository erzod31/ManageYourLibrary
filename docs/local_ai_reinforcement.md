# Reforzar con IA local

Manage Your Library puede usar una capa opcional de IA local para reforzar casos dudosos de metadatos bibliográficos.

La IA local no es una fuente primaria. Solo puede elegir entre candidatos reales que la app ya haya obtenido por análisis local o fuentes bibliográficas permitidas. Si la respuesta contradice ISBN/DOI, scoring local o evidencia fuerte, el archivo queda en revisión.

## Modelos permitidos

La interfaz solo ofrece:

- Qwen3 1.7B Q4 — aprox. 1,4 GB — recomendado
- Qwen3 4B Q4 — aprox. 2,5 GB — más preciso

Los modelos GGUF no se incluyen en el repositorio.

## Runtime esperado

La integración está preparada para llama.cpp portable, no Ollama.

Estructura esperada en una distribución por carpeta:

```text
ai/
  runtime/
    llama-server.exe
    llama-cli.exe
    LICENSES/
  models/
    qwen3-1.7b-q4/
      model.gguf
    qwen3-4b-q4/
      model.gguf
```

Si `ai/models/` no es escribible, la app usa la carpeta de datos local del usuario cuando corresponda. Si falta el runtime o el modelo, la app muestra un estado claro y sigue funcionando sin IA.

## Privacidad y copyright

La IA recibe solo señales mínimas:

- nombre base del archivo, sin ruta completa;
- extensión;
- título, autor, año, ISBN/DOI e idioma detectados;
- señales cortas ya extraídas;
- candidatos bibliográficos reales.

No se envían libros completos, capítulos, páginas largas, rutas privadas ni texto OCR largo. No se usan APIs remotas, cuentas, API keys, Google Books ni OCR en la nube.

## Decisión conservadora

- Confianza local >= 92: la app no llama a IA.
- Confianza local entre 75 y 92: puede llamar a IA si está activada, instalada y disponible.
- Confianza local < 75: revisión.
- Si IA y scoring local no coinciden: revisión.
- Si la IA elige un candidato inexistente o devuelve JSON inválido dos veces: revisión.
- El nombre final se genera con el formato de la app y solo con datos confirmados.

## Notas de distribución

No se debe subir a GitHub:

- modelos `.gguf`;
- descargas parciales;
- `ai/runtime/`;
- `ai/models/`;
- `dist/`, `build/`, cachés o temporales.
