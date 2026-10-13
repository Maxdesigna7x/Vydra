# Uso de Vydra desde la terminal

La CLI ejecuta ProstT5, la cascada de seis MLP y la búsqueda FAISS localmente.
Solo se ejecutan las cabezas correspondientes a la ruta elegida: M1→M2 para
celulares; M1→M3→M4 para virus eucariotas (978 clases); M1→M3→M5 y, si es
estructural, M6 para fagos. FAISS añade contexto de referencia a los fagos.

## Elegir el punto de entrada

En el proyecto completo, desde la carpeta que contiene `vydra`:

```bash
conda activate vydra
./vydra --help
./vydra predict --language es --help
./vydra doctor
```

En el proyecto completo el entorno se crea con `conda env create -f environment.yml`.
CPU ejecuta ProstT5, MLP y FAISS sin CUDA. Auto usa CUDA si PyTorch y FAISS GPU pueden inicializarse; en caso contrario usa CPU. CUDA explícito requiere GPU.
`doctor` revisa dependencias, soporte GPU, los seis pesos y los artefactos
esperados; no ejecuta una predicción completa.

## Entradas y resultados

Elige exactamente una entrada: `--seq`, `--fasta`, `--stdin` o `--embedding`.
Las entradas de secuencia deben contener aminoácidos; la CLI no traduce ADN/ARN.

```bash
./vydra predict --seq "MSTNPKPQRKTKRNTNRRPQDVKFPGGGQIVGGVYLLPRRGPRLG"
./vydra predict --fasta muestras.faa
cat muestras.faa | ./vydra predict --stdin --format jsonl
```

La salida predeterminada es una tabla con ID, longitud, ruta, cluster y
similitud. Para conservar todos los campos, usa un formato estructurado:

```bash
mkdir -p resultados
./vydra predict --fasta muestras.faa --language es \
  --format jsonl --output resultados/predicciones.jsonl
```

| `--format` | Contenido |
|---|---|
| `table` (default) | Resumen legible; no incluye toda la metadata. |
| `json` | Lista JSON con una predicción por proteína y objetos anidados. |
| `jsonl` | Un objeto JSON completo por línea; recomendado para regenerar informes. |
| `csv` | Una fila por proteína; objetos aplanados con nombres como `confidences.M1` y `cluster_annotation.dominant_genus`; `path` separado por `/`. |

Sin `--output`, las predicciones se escriben a stdout y no se crea informe.
Los mensajes del motor, progreso y tiempos se envían a stderr. Con `--output`,
la CLI crea la carpeta destino si hace falta. Guarda también metadata de tiempos
y una copia de las secuencias originales cuando la entrada contiene proteínas.

El informe recupera hasta cinco prototipos por fago con sus metadatos. Permite
filtrar por categoría y contexto de género/familia, y exportar todas las filas
filtradas a CSV o FASTA con encabezados originales. Consulte la
[guía de evidencia y exportación](../docs/EVIDENCIA_BIOLOGICA_Y_EXPORTACION.md).

## Informe automático y archivos entregados

Con `--output` se genera el informe por defecto, para cualquiera de los cuatro
formatos. El ejemplo anterior produce:

```text
resultados/
├── predicciones.jsonl
├── README_ARCHIVOS.txt            # guía de los archivos de resultados
├── README_ARCHIVOS_en.txt
├── README_ARCHIVOS_es.txt
└── informe_inferencia_predicciones/
    ├── informe.html               # abrir en un navegador; funciona offline
    ├── predicciones.jsonl         # copia estructurada para reconstruir el informe
    ├── secuencias.csv.gz          # todas las proteínas y campos disponibles
    ├── origen_archivos.csv
    ├── jerarquia.csv
    ├── asignaciones_taxonomicas.csv
    ├── resolucion_taxonomica.csv
    ├── resolucion_control_umbral.csv
    ├── umbrales_similitud_fagos.csv
    ├── taxones_todos.csv
    ├── taxones_top10.csv
    ├── dominancia.csv
    ├── calidad_anotacion.csv
    ├── procedencia.json
    ├── README.txt                 # guía del informe y copias EN/ES
    ├── README_en.txt
    ├── README_es.txt
    ├── *.png / *.svg              # figuras en inglés
    └── es/                        # las mismas figuras en español
```

El directorio se llama `informe_inferencia_<nombre de salida sin extensión>`.
El HTML está actualmente en inglés, con cascada y porcentajes respecto al padre,
resolución taxonómica, rankings, distribución por etiqueta y control FAISS.
`--language en|es` fija los mensajes de CLI y las guías TXT (default: `en`);
no cambia los nombres de archivos, campos ni etiquetas científicas.

`secuencias.csv.gz` es un CSV comprimido sin pérdida; contiene predicciones,
procedencia y longitudes, pero no las cadenas de aminoácidos. El HTML abre sin
cargarlo. `--sequence-export csv` lo genera sin comprimir; `none` omite solo
esa exportación adicional, conservando resultados, informe y otras tablas.

```bash
./vydra predict --fasta muestras.faa --format csv \
  --output resultados/predicciones.csv --sequence-export none
./vydra predict --fasta muestras.faa --format jsonl \
  --output resultados/solo_predicciones.jsonl --no-report
```

Si falla la generación del informe, las predicciones ya guardadas permanecen
disponibles y la CLI devuelve un error. Se puede regenerar sin repetir modelos
ni necesitar GPU, desde la carpeta `vydra_core/`:

```bash
python inference_report.py --input /ruta/resultados/predicciones.jsonl \
  --output /ruta/resultados/informe_regenerado --language es
```

El generador admite CSV y JSONL completos del motor; para una salida `table` o
`json`, usa el `predicciones.jsonl` guardado dentro del informe. Véase
[guía de salidas e interpretación](SALIDAS.md).

## Embeddings existentes y modo offline

`--embedding` admite `.npy` con forma `(1024,)` o `(n, 1024)`, y `.pt` con
`ID → tensor` o `clase → {ID → tensor}`. Deben ser embeddings ProstT5 de 1024
dimensiones compatibles con los modelos; no se carga el encoder. En `.npy`
se generan IDs `query_1`, `query_2`, etc. La longitud es `0` porque no se dispone
de la secuencia original.

```bash
./vydra predict --embedding embeddings.npy --offline --format json
```

Si faltan los bancos, el comando de descarga está configurado para GitHub
Releases `Maxdesigna7x/Vydra`, etiqueta `artifacts-v1`:

```bash
./vydra download-artifacts
./vydra download-model
./vydra predict --offline --fasta muestras.faa
```

`download-artifacts` omite bancos existentes; `--force` los reemplaza y verifica
su SHA-256. Para descargas privadas puede usar una sesión autenticada de `gh`.
`download-model` guarda el snapshot fijado de `Rostlab/ProstT5_fp16` en `models/prostt5`; con `--directory`
puedes elegir otro destino y luego configurarlo:

```bash
export VYDRA_PROSTT5_PATH=/ruta/a/ProstT5
./vydra predict --offline --fasta muestras.faa
```

## Secuencias largas, batch y memoria

Las proteínas de más de 2048 aa se dividen en ventanas de 2048 con solapamiento
de 512 aa. Se promedian sus embeddings y se conserva una predicción por proteína.
El motor ordena ventanas por longitud, agrupa longitudes similares y calcula
el batch según memoria libre tras cargar ProstT5. Recupera el orden final y,
si ocurre un OOM, reduce el batch a la mitad y reintenta.

| Opción | Uso / default |
|---|---|
| `--device auto`, `cpu` o `cuda` | Dispositivo de ProstT5/MLP/FAISS; default `auto`, GPU compatible o CPU. |
| `--batch-size N` | Batch inicial fijo; mantiene la recuperación por OOM. |
| `--max-batch-size N` | Límite automático; GPU 256, CPU 32. |
| `--memory-fraction F` | Fracción máxima de memoria total; GPU 0.85, CPU 0.75. |
| `--reserve-memory-gb G` | Reserva explícita en GiB; si se omite se calcula. |
| `--length-bin N` | Ancho de buckets; default 128 aa. |

```bash
./vydra predict --fasta muestras.faa \
  --memory-fraction 0.70 --reserve-memory-gb 2 --max-batch-size 64
```

La política inicial GPU se calibró en una RTX 3060 de 11.63 GiB y se escala al
dispositivo detectado. La GUI local admite `VYDRA_BATCH_SIZE`, `VYDRA_MAX_BATCH_SIZE`,
`VYDRA_MEMORY_FRACTION`, `VYDRA_RESERVE_MEMORY_GB` y `VYDRA_LENGTH_BIN`.
ProstT5 se descarga de memoria al terminar los embeddings, también al fallar esa
etapa; MLP/FAISS se conservan para reutilizarlos.

## Modelos locales

La CLI y la GUI reutilizan primero el modelo configurado, el modelo completo del paquete y la caché local. Solo descargan archivos faltantes cuando se permiten descargas. `--offline` las prohíbe. Las secuencias siempre se procesan en el equipo; no se envían a una API de inferencia.
