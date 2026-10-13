<div align="center">
  <img src="docs/images/vydra-icon.webp" width="88" alt="Logo de Vydra">
  <h1>Vydra</h1>
  <p><strong>Clasifica secuencias de proteínas y explora la evidencia biológica de sus predicciones.</strong></p>
  <p><a href="README.md">English</a> · <a href="README.es.md">Español</a> · <a href="https://github.com/Maxdesigna7x/Vydra/issues">Reportar un problema</a></p>
  <p>Interfaz local en el navegador · CPU o GPU NVIDIA · Informes interactivos · Exportación CSV y FASTA</p>
</div>

Vydra analiza **secuencias de aminoácidos** en archivos FASTA de proteínas. Distingue proteínas celulares y virales, separa bacteriófagos de virus eucariotas y predice diez componentes estructurales de fagos. Para proteínas de fagos también recupera referencias cercanas y sus anotaciones, para que puedas revisar la evidencia.

**Software de investigación:** las predicciones y anotaciones de referencia apoyan la interpretación biológica. No demuestran la especie, el hospedero ni una función experimentalmente confirmada de la proteína consultada.

[Instalación](#instalar-una-vez) · [Usar la interfaz](#analizar-tus-proteínas) · [Leer los resultados](#entender-los-resultados) · [Exportar proteínas](#filtrar-y-exportar) · [Resolver problemas](#resolver-problemas)

## Qué obtienes

| Resultado | Qué te informa |
|---|---|
| Clasificación celular | Bacteria, Archaea o Eukaryota. |
| Clasificación viral | Proteína de fago o de virus eucariota. |
| Grupo de virus eucariotas | Uno de 978 grupos de proteínas, con anotaciones publicadas de VirDetect-AI. No son 978 especies ni 978 funciones distintas. |
| Categoría estructural de fago | Placa basal, collar, unión cabeza–cola, cápside principal/minoritaria, cola principal/minoritaria, portal, fibra de cola o vaina de cola. |
| Evidencia de referencia para fagos | Hasta cinco prototipos cercanos de la clase predicha, con similitudes y anotaciones individuales, más el contexto del cluster asignado. |
| Informe y archivos | HTML interactivo, tablas completas de predicciones, procedencia de entradas, tiempos y exportaciones filtradas. |

Toda la inferencia se ejecuta en tu equipo. Solo hace falta internet para obtener software, modelos y bancos de referencia cuando aún no están instalados.

## Antes de comenzar

- **Entrada:** archivos FASTA de proteínas con aminoácidos. El ADN/ARN debe traducirse previamente con un flujo apropiado de predicción de genes; Vydra no traduce nucleótidos.
- **Plataforma:** el entorno local está validado en Linux. Otros sistemas operativos no se han validado.
- **Software:** Git y [Conda](https://docs.conda.io/projects/conda/en/stable/user-guide/install/index.html). Conda crea un entorno aislado con las dependencias; no necesitas instalar cada paquete de Python por separado.
- **Disco:** calcula unos 25 GB libres para software, modelos y corridas pequeñas. Entradas e informes grandes requieren espacio adicional.

| Ejecución | Entorno | Orientación de hardware |
|---|---|---|
| CPU | `vydra-cpu` | No requiere GPU; la inferencia tarda más. |
| GPU NVIDIA | `vydra` | Requiere CUDA; validado en RTX 3060 de 12 GB de VRAM. Este entorno también admite CPU. |
| Abrir un informe guardado | No requiere Conda | Navegador moderno; la memoria necesaria aumenta con el tamaño del informe. |

**Se recomiendan 32 GB de RAM.** 16 GB es un mínimo práctico estimado para entradas pequeñas y batch 1, no un mínimo certificado. Proteínas largas y colecciones grandes pueden requerir más. Consulta la [validación CPU/GPU y las mediciones de RAM](docs/CPU_GPU_VALIDATION.md).

## Instalar una vez

Abre una terminal y clona el repositorio:

```bash
git clone https://github.com/Maxdesigna7x/Vydra.git
cd Vydra
```

Elige **un solo** entorno:

<details>
<summary><strong>Instalación CPU — no requiere GPU NVIDIA</strong></summary>

```bash
conda env create -f environment-cpu.yml
conda activate vydra-cpu
```

</details>

<details>
<summary><strong>Instalación con GPU NVIDIA</strong></summary>

```bash
conda env create -f environment.yml
conda activate vydra
```

</details>

Con ese entorno activo, descarga los modelos y comprueba la instalación:

```bash
./vydra download-artifacts
./vydra download-model
./vydra doctor
```

Los pesos del clasificador y las anotaciones de referencia se incluyen en el repositorio. Los dos bancos grandes se descargan aparte, aproximadamente 1.6 GB en total; el encoder ProstT5 fijado requiere unos 5.3 GB. Las descargas se reutilizan en corridas posteriores. No instales las variantes CPU y GPU de FAISS juntas en un mismo entorno.

## Analizar tus proteínas

Después de instalar, abre una terminal en la carpeta del repositorio. El lanzador activa Conda automáticamente y abre la interfaz:

```bash
# Entorno para GPU, que también permite inferencia CPU
./run_vydra_ui.sh

# Entorno exclusivo de CPU
VYDRA_CONDA_ENV=vydra-cpu ./run_vydra_ui.sh
```

![Interfaz local de Vydra para elegir proteínas y carpeta de resultados](docs/images/local-gui-dark.png)

1. Selecciona un **archivo FASTA de proteínas** o una **carpeta**. Se revisan las subcarpetas; conservar un archivo por muestra permite rastrear su procedencia.
2. Elige una **carpeta de salida nueva o vacía, fuera de la carpeta de entrada**.
3. Mantén activado **Generate inference report**. El dispositivo automático usa una GPU compatible cuando está disponible; en caso contrario, CPU.
4. Inicia la corrida. Se muestra la etapa de procesamiento, el número de proteínas clasificadas cuando está disponible y el tiempo transcurrido.
5. Selecciona la corrida completada en el historial para abrir sus resultados. También puedes abrir `informe_inferencia/informe.html` directamente en un navegador.

**Mantén abierta la terminal del servidor.** Cerrar la pestaña deja la inferencia en ejecución; Ctrl+C en la terminal detiene el servidor y su corrida activa. Cancelar conserva archivos parciales: vuelve a intentarlo en una carpeta nueva.

La interfaz y el informe están actualmente en inglés. La CLI admite mensajes en español e inglés. Las opciones avanzadas incluyen batch, dispositivo, permiso para descargar modelos y generación del informe. **Check installation** es opcional: no hace falta pulsarlo para usar los modelos locales.

## Entender los resultados

El informe separa **predicciones del modelo**, **anotaciones de referencias cercanas** y **contexto del grupo de referencia**.

<p align="center">
  <a href="docs/images/inference-results.jpg"><img src="docs/images/inference-results.jpg" width="560" alt="Informe de Vydra con clasificación jerárquica, evidencia de fagos, tiempos y tabla filtrable con exportación CSV y FASTA"></a>
</p>

*Ejemplo de un informe con 293 registros de proteínas. Los conteos y tiempos corresponden a esta corrida; no son una medida de exactitud. Haz clic en la imagen para verla con resolución completa.*

- **Classification overview:** conteos de proteínas predichas en cada etapa. Los porcentajes usan la categoría padre correspondiente; no representan abundancia de organismos o virus.
- **Phage reference evidence:** cinco prototipos cercanos de la clase predicha, incluidos otros clusters como alternativas. La vista inicial muestra género/familia solo si todos los vecinos con ese campo coinciden. Abre el detalle de una proteína para ver cuántas anotaciones hay y dónde discrepan.
- **Cluster context:** vista secundaria del cluster asignado completo, que puede ser mayor y más diverso que el vecindario cercano.
- **Contexto de clase de virus eucariotas:** anotaciones publicadas del grupo, con accesión representativa, descripción, categoría funcional y contexto taxonómico cuando existe. Esta rama no realiza recuperación FAISS.
- **Tiempos:** inferencia y procesamiento total, incluida la generación del informe cuando está activa; son tiempos de toda la corrida, no de cada proteína.

Hay tres cantidades que se deben interpretar por separado:

| Cantidad | Interpretación |
|---|---|
| Puntuación del clasificador | Preferencia softmax por una categoría en una etapa; no es exactitud biológica calibrada. |
| Similitud de referencia | Similitud coseno entre embeddings; no es identidad de aminoácidos ni probabilidad de compartir función. |
| Coincidencia de anotaciones | Acuerdo entre referencias con información conocida, acompañado de cobertura; no son necesariamente cinco organismos independientes. |

Para fagos se informa un umbral de construcción del cluster. Superarlo **no** valida la consulta; el motor conserva la asignación al cluster más cercano incluso por debajo del umbral. `Hypothetical protein` y `uncharacterized protein` indican que esa anotación fuente no aporta una función específica. Vydra conserva el texto como información de referencia, sin atribuirlo como función conocida de la consulta.

## Filtrar y exportar

La tabla final permite combinar filtros como **Collar + género de referencia + familia de referencia**. Elige si la taxonomía de fagos corresponde a los cinco prototipos cercanos o al cluster asignado.

- **Export filtered CSV:** exporta todas las filas que coinciden, con evidencia y anotaciones.
- **Export filtered FASTA:** exporta todas las proteínas originales que coinciden, incluidas las de otras páginas. Conserva encabezados completos, IDs originales repetidos, residuos originales y `*` terminal; solo normaliza el formato de las líneas.

El HTML incluye las secuencias originales comprimidas para exportar FASTA sin conexión. Requiere un navegador moderno y secuencias originales disponibles. Las entradas solo por embeddings y las corridas antiguas sin copia de las secuencias no permiten esa exportación. Regenerar un informe antiguo tampoco añade cinco vecinos: para recuperarlos hace falta una nueva inferencia.

### Archivos que conviene conservar

Las corridas de la GUI guardan estos archivos en la carpeta de salida:

| Archivo | Uso |
|---|---|
| `informe_inferencia/informe.html` | Explorar resultados; funciona sin conexión. |
| `predicciones_completas.csv` / `.jsonl` | Predicciones y evidencia completas por proteína; CSV con columnas numeradas para cinco vecinos. |
| `manifest_secuencias.csv` | Relación de IDs internos con encabezados, archivos y longitudes originales. |
| `secuencias_excluidas.csv` | Registros excluidos durante la preparación y sus motivos. |
| `original_sequences.jsonl` | Encabezados y residuos originales para exportar FASTA y regenerar informes. |
| `metadata_inferencia.json` | Configuración, rutas, modelos, estado y tiempos. |
| `informe_inferencia/tiempos.csv` | Tiempos de inferencia, informe y procesamiento total. |
| `informe_inferencia/secuencias.csv.gz` | Tabla completa adicional, comprimida sin pérdida. |

El CSV aumenta con las anotaciones de cinco vecinos; gzip ahorra espacio porque muchos textos de referencia se repiten. El HTML también crece con la evidencia y las secuencias comprimidas. Conserva juntas predicciones, entradas, copias de secuencias y metadata para reproducibilidad. [Guía completa de salidas](vydra_core/SALIDAS.md).

## Resolver problemas

| Problema | Qué hacer |
|---|---|
| No se encuentra `conda` | Instala Conda, abre otra terminal y sigue sus instrucciones de inicialización. El lanzador también admite `VYDRA_CONDA_ROOT=/ruta/a/conda`. |
| El lanzador no activa el entorno | Termina la instalación; para CPU indica `VYDRA_CONDA_ENV=vydra-cpu`. |
| Faltan modelos o bancos | Activa el entorno elegido y ejecuta `download-artifacts`, `download-model` y `doctor`. |
| CUDA no está disponible | Selecciona CPU o Automatic; la ejecución CPU no requiere CUDA. |
| Memoria insuficiente | Cierra otros procesos pesados y prueba Batch size = 1. Entradas grandes pueden requerir más RAM. |
| Se excluyeron registros | Revisa `secuencias_excluidas.csv` y comprueba que las entradas sean proteínas. |
| FASTA no se puede exportar | Comprueba que haya copia de las secuencias originales y usa un navegador moderno. Los embeddings solos no permiten recuperar residuos. |
| No se abre el navegador | Ejecuta `./run_vydra_ui.sh --no-browser --port 8732` y abre la URL local indicada. Para CPU añade la variable del entorno correspondiente. |

Para trabajar sin conexión, desmarca **Allow model downloads** después de instalar modelos y bancos. Esto prohíbe descargar lo que falte; los modelos locales siguen utilizándose. [FAQ de uso](docs/GUI_FAQ.md).

## Uso desde la terminal

Para automatizar o integrar flujos mayores, activa el entorno Conda apropiado:

```bash
./vydra predict --fasta proteins.faa --format csv --output results/predictions.csv
./vydra predict --offline --device cpu --fasta proteins.faa --format jsonl --output results/predictions.jsonl
./vydra predict --embedding embeddings.npy --offline --format json
```

Con `--output`, la CLI genera el informe por defecto; `--no-report` lo desactiva. Sin `--output`, escribe las predicciones en la terminal y no genera informe. Las carpetas del informe de CLI se llaman `informe_inferencia_<nombre_salida>/`. [Guía CLI](vydra_core/CLI.md).

<details>
<summary><strong>Descripción técnica y validación</strong></summary>

ProstT5 produce un embedding de 1024 dimensiones compartido por seis cabezas MLP. Cada proteína visita únicamente las decisiones de su ruta predicha.

| Cabeza | Decisión |
|---|---|
| M1 | Celular / viral |
| M2 | Bacteria / Archaea / Eukaryota |
| M3 | Fago / virus eucariota |
| M4 | 978 grupos de proteínas virales eucariotas |
| M5 | Fago estructural / no estructural |
| M6 | Diez categorías estructurales |

La asignación de fagos usa búsqueda exacta FAISS por producto interno de embeddings normalizados, dentro de la clase predicha. Los cinco prototipos aportan evidencia descriptiva; el primero conserva la asignación previa al cluster más cercano. Las proteínas de más de 2048 aminoácidos se procesan con ventanas solapadas cuyos embeddings se promedian.

Las comprobaciones de ejecución CPU/GPU y las mediciones de RAM se documentan por separado de la calidad biológica. La evaluación interna de cada cabeza no demuestra exactitud de todo el flujo en muestras externas arbitrarias. Cobertura de referencias, anotaciones, fragmentos cortos y errores en etapas anteriores afectan la interpretación. Las reglas nuevas de transferencia funcional o taxonómica requieren evaluación independiente.

- [Diseño de evidencia biológica y exportaciones](docs/EVIDENCIA_BIOLOGICA_Y_EXPORTACION.md)
- [Validación CPU/GPU](docs/CPU_GPU_VALIDATION.md)
- [Benchmark de batch RTX 3060](docs/BATCH_BENCHMARK_RTX3060.md)
- [Figura histórica de evaluación de clasificadores](docs/images/classifiers-en.png)

Las regresiones de software se comprueban con `python -m unittest discover -s tests -p 'test_*.py'` en el entorno instalado. Estas pruebas no certifican exactitud biológica.

</details>

## Documentación y soporte

CLI actual: **0.4.0**. [Cambios de esta versión](CHANGELOG.md).

- [Guía GUI](vydra_core/GUI.md) y [FAQ de uso](docs/GUI_FAQ.md)
- [Guía CLI](vydra_core/CLI.md) y [diccionario de salidas](vydra_core/SALIDAS.md)
- [Evidencia de referencia, FASTA y tiempos](docs/EVIDENCIA_BIOLOGICA_Y_EXPORTACION.md)
- [Guía de informes](docs/INFORMES_INFERENCIA.md)
- [Reportar un problema](https://github.com/Maxdesigna7x/Vydra/issues): incluye comando/configuración, log del error, dispositivo y revisión de software. Una entrada pequeña que reproduzca el problema ayuda cuando se puede compartir.

Vydra forma parte de una tesis en desarrollo. Hasta que exista una publicación formal, cita este repositorio y conserva el commit, versiones de modelos/referencias y parámetros utilizados. La captura de resultados no es evidencia de exactitud predictiva.
