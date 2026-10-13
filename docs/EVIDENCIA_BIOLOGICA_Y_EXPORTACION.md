# Evidencia biológica y exportación de Vydra

Actualización del motor local: 13 de octubre de 2026. No cambia pesos, embeddings,
clusters ni clases. Viral eukaryotic continúa con M4 y su diccionario de clase;
celulares continúan con M2. No se incorporan búsquedas en esas ramas.

## Fagos: referencias cercanas primero

Se recuperan hasta cinco prototipos del banco FAISS de la clase predicha. Para
estructurales se restringe a la categoría M6; para no estructurales usa
`phage_non_struct`. Incluye clusters alternativos de esa clase. No busca
exhaustivamente entre todos los miembros originales ni entre otras clases M6.

El primer vecino conserva la asignación anterior de k=1, incluso ante empates.
`cluster_id`, `cluster_similarity` y `cluster_nearest_seq_id` conservan su significado.
El umbral informado es de construcción: no acepta/rechaza ni valida consultas.

`nearest_neighbors` conserva ranking, ID, cluster, similitud, clase y los metadatos
individuales disponibles: accesión, IDs PHROG/locales, producto, organismo, nombre
viral, género, familia, hospedero, longitudes, país, fecha, FASTA y encabezado fuente.
El cruce usa `(dataset_type, class_name, seq_id)`; jamás rellena anotaciones
ausentes con las del representante del cluster.

`neighbor_summary` es descriptivo. Para X = género, familia, producto u hospedero:

| Campo | Significado |
|---|---|
| `n_neighbors`, `n_distinct_clusters` | Referencias recuperadas y clusters presentes. |
| `X_known` | Vecinos con X anotado. |
| `X_dominant`, `X_dominant_count` | Valor más frecuente y su conteo; en empate, el primero en el ranking. |
| `X_unique`, `X_values` | Valores distintos y distribución completa. |
| `X_coverage` | Con X / recuperados. |
| `X_agreement` | Con el valor dominante / con X; nulo cuando no hay X. |
| `n_with_function_description` | Descripciones no genéricas, incluidas candidatas; no cuenta funciones comprobadas. |

Las referencias pueden ser redundantes o contener errores. Estas cifras no son
probabilidades de acierto. Coincidir en taxonomía no demuestra función compartida.
El resumen completo del cluster se conserva como contexto secundario.

## Descripciones funcionales

El texto original nunca se reemplaza. `function_annotation_status` distingue:

- `unavailable`: sin descripción.
- `unspecified`: hypothetical, uncharacterized o unknown function; no informa función específica.
- `candidate_description`: putative, probable o predicted; descripción candidata.
- `description_available`: otra descripción disponible; no demuestra especificidad ni respaldo experimental.

Son reglas conservadoras sobre texto, no una auditoría de evidencia biológica.
M6 predice un componente estructural; la anotación del vecino se presenta por
separado. `mixed_or_functional` conserva su código interno, pero el texto visible
indica contexto mixto/sin predominio suficiente, sin atribuir función compartida.

## HTML y CSV

El detalle de una proteína muestra primero sus vecinos y deja el cluster
desplegable. La perspectiva inicial de fagos muestra una etiqueta de género o
familia solo si todos los vecinos con ese campo coinciden. Puede haber solo una
referencia anotada entre cinco: el detalle informa coincidencias, campos conocidos
y diversidad. Es contexto de referencia, no predicción taxonómica calibrada.
Una perspectiva alternativa conserva el contexto del cluster asignado.

M4 muestra también el diccionario publicado de VirDetect-AI: descripción,
categoría funcional, representante, familia, hospedero y tipo de genoma. Los
resúmenes taxonómicos locales siguen siendo una fuente distinta; no se equiparan
sus reglas con las etiquetas oficiales de Table S1.

CSV/JSON conservan toda la evidencia. CSV usa columnas `nearest_neighbors.1.*`
a `nearest_neighbors.5.*`; `*_values` guarda JSON en una celda para evitar
columnas variables por taxón. Los CSV y figuras taxonómicas históricos conservan
los conteos basados en grupos; el selector de vecinos del HTML añade otra
perspectiva explícita. El CSV filtrado del HTML conserva vecinos, resumen local,
contexto del cluster y diccionario M4 como campos JSON.

## FASTA de filas filtradas

El botón exporta todas las filas que cumplen ámbito, selección, búsqueda y
filtros de columnas, incluidas otras páginas. Se pueden combinar clase M6,
género y familia de referencia. La taxonomía usada depende de la perspectiva
elegida: vecinos o cluster.

Conserva encabezados completos, IDs repetidos, mayúsculas/minúsculas y residuos
originales, incluido el * terminal. Solo normaliza saltos y envuelve a 80 caracteres.
No añade predicciones al encabezado ni exporta la secuencia canónica del modelo.
Los registros excluidos del análisis no están en la selección.

CLI guarda `<salida>.original_sequences.jsonl`; GUI/carpetas guardan
`original_sequences.jsonl`. El HTML contiene una copia gzip/base64 y la
descomprime al exportar, sin necesitar los FASTA fuente ni conexión a internet.
Su tamaño crece con el contenido comprimido; exportar requiere memoria para
descomprimirlo. Usa DecompressionStream de navegadores modernos.

Entradas solo por embeddings y reportes antiguos sin snapshot no tienen FASTA
exportable. El botón se deshabilita cuando cualquier fila seleccionada carece
de secuencia, o falta soporte del navegador. No se generan archivos parciales
silenciosamente. Regenerar reportes antiguos no inventa vecinos ni secuencias.

## Tiempos de corrida

`run_inference_seconds` en resultados individuales es tiempo de la corrida,
no tiempo por proteína. En CLI abarca carga, embeddings y clasificación. En
metadata de GUI/carpetas, `inference_seconds` incluye preparación y posprocesado.
`report_seconds` mide generación del reporte; `total_processing_seconds` incluye
resultados y reporte. Puede incluir la primera descarga de modelos. Las escrituras
finales de metadata/etiquetas de tiempo quedan fuera de la medición.

CLI imprime tiempos en stderr y guarda `<salida>.metadata.json`. Los reportes
guardan metadata, `procedencia.json`, `tiempos.csv` y tiempos visibles en HTML.
GUI/carpetas mantienen `metadata_inferencia.json`. Se usa reloj monotónico;
no se estiman tiempos para resultados antiguos.

## Artefactos y reproducción

El CSV comprimido `vydra_core/artifacts/prototype_sequence_metadata.csv.gz` aporta
metadatos para los prototipos exactos desplegados. Regeneración:

```bash
python scripts/export_prototype_metadata.py
```

Regenerar este artefacto requiere las tablas de metadatos y mapas CSV de
prototipos del conjunto de investigación, que no se distribuye completo en
el repositorio público. La instalación normal utiliza el CSV comprimido incluido.

Distribuirlo junto con `prototype_metadata_provenance.json`, que registra hashes,
fuentes y faltantes. Hay 268124 prototipos y 268119 coincidencias de metadatos;
los cinco restantes permanecen sin anotación. Los bancos .pt no cambian.
`vydra doctor` verifica presencia del nuevo artefacto.

## Trabajo futuro

- Recuperación para M4 y clases celulares.
- Ranking exhaustivo dentro de clusters y control de redundancia.
- Validación independiente de transferencia taxonómica/funcional.
- Alineamientos, dominios y evidencia experimental.
- Exportación por streaming para millones de proteínas.

Estas ampliaciones no se incluyen en este cambio.

## Verificación

Pruebas de regresión del motor, CSV, metadatos y conservación de secuencias:

```bash
python -m unittest discover -s tests -p 'test_*.py'
python tests/create_reference_evidence_fixture.py /tmp/vydra-reference-fixture
node tests/browser_reference_evidence.cjs /tmp/vydra-reference-fixture/informe.html
```

La prueba de navegador necesita Playwright y Chromium. Se pueden indicar sus
rutas con `VYDRA_PLAYWRIGHT_PACKAGE` y `VYDRA_CHROMIUM_EXECUTABLE`. Comprueba
filtros simultáneos, exportación de ocho filas con solo seis visibles, encabezados
repetidos, residuos originales, CSV, metadata M4 y funcionamiento del HTML copiado.
La fixture está marcada como sintética. Las pruebas de software no validan
la exactitud biológica de las asignaciones.
