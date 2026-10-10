# Salidas de Vydra y cómo interpretarlas

Esta guía describe la implementación local revisada el 5 de octubre de 2026.
La [CLI](CLI.md), la [web/API](README.md) y el procesador de carpetas del proyecto
comparten motor, pero entregan archivos y esquemas diferentes.

## Predicción completa de la CLI

Cada proteína tiene una ruta jerárquica y confianza para las cabezas visitadas.
No se ejecutan ni se reportan las seis decisiones para cada proteína.

| Campo | Significado |
|---|---|
| `seq_id` | ID del registro; si hay IDs repetidos, la CLI agrega `R0000001:` (y el índice correspondiente) a todos los registros para hacerlos únicos. |
| `original_id`, `original_header` | ID y encabezado previos al prefijo. |
| `length`, `chunked` | Longitud original y si se usaron ventanas; longitud 0 para entrada por embeddings. |
| `path`, `path_text` | Ruta como lista y texto, por ejemplo `viral / phage / structural / major_capsid`. |
| `confidences` | Probabilidad softmax de la clase elegida por cabeza, como `M1`, `M3`, `M5`, `M6`; no es precisión ni probabilidad conjunta de toda la ruta. |
| `cluster_branch`, `cluster_class` | Rama FAISS y clase de búsqueda; no estructural usa `phage_non_struct`. |
| `cluster_id` | Cluster de referencia; `-1` indica ausencia de asignación. Se interpreta junto con rama y clase, no como ID global independiente. |
| `cluster_similarity` | Producto interno de embeddings normalizados, equivalente a similitud coseno con el prototipo más cercano. |
| `cluster_nearest_seq_id` | ID del prototipo/medoid más cercano, no una búsqueda exhaustiva entre todas las secuencias originales. |
| `cluster_similarity_threshold` | Umbral de referencia informado para esa clase. El motor no rechaza al vecino por estar bajo él. |
| `cluster_annotation` | Contexto del cluster: tamaño, cobertura de metadata, taxones/productos dominantes, purezas, representante y estadísticas de longitud. |
| `cluster_biological_label` | Etiqueta resumida del contexto de referencia. |
| `viral_euk_class_metadata` | Diccionario de la clase M4 basado en VirDetect-AI: clase, familia, género, hospedero, descripción, función y representante, cuando están disponibles. |
| `source_*` | Archivo, carpeta, ruta y SHA-256 de la entrada cuando se proporcionó un archivo; no están disponibles para texto directo/stdin. |

Las etiquetas guardadas usan `eukariota` tanto en M2 como en M3; la rama previa
(`cellular` o `viral`) permite distinguirlas. M4 usa etiquetas `viral/euk/0`
a `viral/euk/977`. Los JSON/JSONL mantienen objetos anidados; el CSV usa puntos
para sus subcampos, por ejemplo `confidences.M6`. Incluye la unión de campos
de todas las proteínas, aunque la primera fila sea celular.

Para celulares y virus eucariotas no hay búsqueda de cluster de fago:
`cluster_id=-1`, similitud ausente (`null` en JSON/JSONL) y campos FAISS vacíos.
Una anotación vacía tampoco prueba ausencia biológica; indica que no hay
metadata disponible. Si falta el banco no estructural, el motor omite esa
asignación; `doctor` lo identifica como artefacto faltante. Se recomienda
comprobar ambos bancos antes de inferir.

## Informe HTML y tablas derivadas

La CLI con `--output` crea `informe_inferencia_<nombre>/`. El procesador de
carpetas crea `informe_inferencia/`. El informe se abre desde `informe.html`,
funciona offline e incorpora selector EN/ES. Las figuras se exportan en PNG/SVG
(en inglés y en `es/`); las guías TXT se entregan en ambos idiomas.

| Archivo | Para qué sirve |
|---|---|
| `predicciones.jsonl` | Copia completa creada por la CLI para reconstruir informes, incluso si la salida principal era tabla/JSON. |
| `secuencias.csv.gz` | Exportación adicional de todas las proteínas celulares y virales, con campos disponibles y procedencia; gzip sin pérdida, sin cadenas de aminoácidos. |
| `origen_archivos.csv` | Conteos por archivo y datos de procedencia. |
| `jerarquia.csv` | Conteos por rama/ámbito y porcentajes respecto al padre y total. |
| `resolucion_taxonomica.csv` | Mejor nivel de contexto disponible, con categorías exclusivas por grupo. |
| `resolucion_control_umbral.csv` | Resolución separando casos FAISS bajo el umbral informado. |
| `umbrales_similitud_fagos.csv` | Umbral informado, conteos y distribución de similitud por clase. |
| `taxones_todos.csv`, `taxones_top10.csv` | Rankings completos y diez etiquetas más frecuentes, con denominadores y acumulados. |
| `dominancia.csv` | Cobertura, Top 1/Top 10 y concentración Simpson. |
| `calidad_anotacion.csv` | Procedencia de anotaciones y control bajo umbral. |
| `asignaciones_taxonomicas.csv` | Auditoría por proteína viral; no incluye celulares. |
| `procedencia.json` | Hash de entrada, referencia taxonómica usada, idioma, reglas y comprobaciones del informe. |
| `README.txt`, `README_en.txt`, `README_es.txt` | Guías breves de archivos; en la carpeta de resultados se generan `README_ARCHIVOS*.txt`. |

`--sequence-export csv|none` cambia únicamente la exportación adicional
`secuencias.csv.gz`; no elimina las predicciones principales. El generador
independiente admite CSV/JSONL completos del motor y no requiere GPU. Una
corrida con `metadata_inferencia.json` solo se acepta si su estado es
`complete`. No usar archivos temporales como entrega terminada.

Para Viral_Euk, el informe puede enriquecer las clases con el resumen taxonómico
local del proyecto, si existe, y registra su hash. En un clone independiente
puede no estar disponible: se mantienen las anotaciones presentes en la entrada.
El generador admite `--viral-euk-taxonomy /ruta/resumen.csv` y
`--no-taxonomy-enrichment`. El diccionario curado `viral_euk_class_metadata`
y el resumen de cobertura/pureza son fuentes distintas y no garantizan idéntica
resolución taxonómica.

## Inferencia de carpetas en el proyecto completo

En el proyecto de investigación completo existe también este script. En el repositorio distribuido se recomienda seleccionar Folder en la GUI:

```bash
conda activate vydra
python scripts/infer_protein_folder.py --input /ruta/proteinas \
  --output /ruta/nueva_corrida --device cuda --language es
```

El destino debe ser nuevo o vacío. Busca recursivamente `.faa`, `.fasta`, `.fa`,
`.fas`, `.fna` y `.ffn`, sin distinguir mayúsculas. Revisa contenido: excluye
registros vacíos, símbolos no proteicos y secuencias compuestas solo por letras
del alfabeto IUPAC de nucleótidos. Esto último puede excluir proteínas ambiguas;
no traduce secuencias de ADN/ARN. Retira un `*` terminal solo de la entrada del
modelo, conservando la longitud original. Ordena proteínas por longitud y usa
IDs internos por archivo/registro, vinculados al encabezado original.

Además del informe, entrega:

| Archivo | Contenido |
|---|---|
| `predicciones_completas.jsonl`, `predicciones_completas.csv` | Predicciones definitivas enriquecidas con archivo/carpeta, encabezado y longitudes. |
| `manifest_secuencias.csv` | Correspondencia de ID interno, origen, hash y registro original. |
| `secuencias_excluidas.csv` | Registros omitidos y motivos. |
| `resumen_general.json` | Conteos globales. |
| `resumen_por_archivo.csv`, `resumen_por_carpeta.csv` | Conteos y estadísticas agrupados por origen. |
| `metadata_inferencia.json` | Estado, configuración, modelo/revisión, rutas y tiempos. |
| `input_proteinas_ordenadas.faa` | Entrada preparada para el motor. |
| `registro_ejecucion.log`, `comandos_ejecucion.txt` | Registro y comandos de ejecución. |

`predicciones_motor_temporal.jsonl` es intermedio, no la salida final.
`--no-report` desactiva el informe; `--model-path`, `VYDRA_PROSTT5_PATH` o la
caché fijada de `Rostlab/ProstT5_fp16` seleccionan el encoder. Sin copia local,
lo descarga salvo que se use `--offline`. Este flujo usa una referencia de
encoder distinta del default `Rostlab/ProstT5` de la CLI; conservar la metadata
para reproducir una corrida. Si falla solo el informe, las predicciones
completas ya guardadas se pueden reutilizar.

```bash
python scripts/report_inference.py \
  --input /ruta/nueva_corrida/predicciones_completas.jsonl --language es
```

## Salida de la GUI local

La GUI usa el mismo motor y conserva predicciones completas CSV/JSONL, manifiesto, exclusiones, resúmenes e informe interactivo. Las ejecuciones completadas abren el informe desde el historial.

## Lectura biológica

- La confianza MLP y la similitud FAISS son medidas diferentes. Ninguna establece por sí sola taxonomía o identidad de aminoácidos.
- El motor conserva el vecino más cercano aunque esté bajo `cluster_similarity_threshold`. El informe lo señala después; cumplir ese umbral no es una política de aceptación taxonómica validada.
- Familias, géneros y hospederos son contexto de las referencias. El informe no certifica especie para la proteína nueva.
- Los porcentajes cuentan proteínas, no organismos, genomas ni abundancia de virus. En la cascada se calculan respecto al padre; los rankings explicitan si el denominador es el grupo completo o solo los registros con etiqueta.
- La resolución exclusiva usa el mejor nivel disponible; los rankings independientes de género y familia pueden incluir la misma proteína.
