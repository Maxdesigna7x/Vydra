<div align="center">
  <p>
    <a href="README.md"><img alt="English" src="https://img.shields.io/badge/Language-English-2563EB?style=for-the-badge"></a>
    <a href="README.es.md"><img alt="Español" src="https://img.shields.io/badge/Idioma-Español-EAB308?style=for-the-badge"></a>
  </p>
  <img src="docs/images/vydra-icon.webp" width="96" alt="Vydra logo">
  <h1>Vydra</h1>
  <p><strong>Clasificación jerárquica y contextualización de proteínas virales con ProstT5, MLP y FAISS.</strong></p>
  <p>
    <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white">
    <img alt="PyTorch" src="https://img.shields.io/badge/PyTorch-2.1%2B-EE4C2C?logo=pytorch&logoColor=white">
    <img alt="CLI" src="https://img.shields.io/badge/interface-CLI-172B4D">
    <img alt="CUDA optional" src="https://img.shields.io/badge/CUDA-optional-76B900?logo=nvidia&logoColor=white">
  </p>
</div>

Vydra recibe una secuencia de proteína y la conduce por una cascada de seis
clasificadores. Distingue proteínas celulares y virales, separa bacteriófagos de
virus eucariotas y, para bacteriófagos, identifica proteínas estructurales y su
clase funcional. Finalmente busca vecinos de referencia para aportar contexto
biológico interpretable.

> **Estado:** proyecto de investigación en desarrollo. Las asignaciones FAISS
> aportan contexto por similitud y no deben interpretarse como una clasificación
> taxonómica directa de la consulta.

![Jerarquía completa de Vydra](docs/images/diagram-en.png)

## Qué puede predecir

La jerarquía comparte un embedding ProstT5 de 1,024 dimensiones:

| Modelo | Decisión |
|---|---|
| M1 | Viral o celular |
| M2 | Bacteria, Archaea o Eukaryota |
| M3 | Bacteriófago o virus eucariota |
| M4 | Una de 978 clases de virus eucariotas |
| M5 | Proteína de fago estructural o no estructural |
| M6 | Una de 10 clases estructurales de fago |

Las clases estructurales son: `baseplate`, `collar`, `head_tail_joining`,
`major_capsid`, `major_tail`, `minor_capsid`, `minor_tail`, `portal`,
`tail_fiber` y `tail_sheath`.

## Inicio rápido

### 1. Clonar e instalar

```bash
git clone https://github.com/Maxdesigna7x/Vydra.git
cd Vydra
conda env create -f environment.yml
conda activate vydra
```

### 2. Descargar los artefactos grandes

Los pesos MLP están incluidos en el repositorio. Los bancos FAISS se publican
separadamente en GitHub Releases porque juntos ocupan aproximadamente 1.6 GB:

```bash
./vydra download-artifacts
```

Para clasificar secuencias crudas también se necesita ProstT5. Este comando lo
guarda dentro del bundle para usos posteriores sin conexión:

```bash
./vydra download-model
```

Comprueba que todo esté listo:

```bash
./vydra doctor
```

### 3. Ejecutar una predicción

```bash
./vydra predict --seq "MSTNPKPQRKTKRNTNRRPQDVKFPGGGQIVGGVYLLPRRGPRLG"
```

Con un FASTA y salida CSV:

```bash
./vydra predict --fasta proteins.fasta --format csv --output predictions.csv
```

Desde un pipe:

```bash
cat proteins.fasta | ./vydra predict --stdin --format jsonl
```

Si ya tienes embeddings ProstT5 normalizados de 1,024 dimensiones:

```bash
./vydra predict --embedding embeddings.npy --offline --format json
```

La CLI admite `table`, `json`, `jsonl` y `csv`, detecta CUDA automáticamente y
permite forzar `--device cpu` o `--device cuda`.

## Ejecución offline

Después de ejecutar `download-artifacts` y `download-model`, la inferencia puede
trabajar sin red:

```bash
./vydra predict --offline --fasta proteins.fasta
```

También puedes apuntar a una instalación local existente de ProstT5:

```bash
export VYDRA_PROSTT5_PATH=/ruta/local/ProstT5
./vydra predict --offline --fasta proteins.fasta
```

## Cómo funciona

```text
Secuencia
   │
   ▼
ProstT5 → embedding de 1,024 dimensiones
   │
   ▼
M1: celular ──────────────► M2: Bacteria / Archaea / Eukaryota
 │
 └── viral ───────────────► M3: virus eucariota / bacteriófago
                              │                    │
                              ▼                    ▼
                         M4: 978 clases      M5: estructural / no estructural
                                                   │
                                                   ▼
                                             M6: 10 clases
                                                   │
                                                   ▼
                                      FAISS + contexto biológico
```

Las secuencias mayores de 2,048 aminoácidos se dividen en ventanas solapadas y
sus embeddings se promedian. La búsqueda final usa producto interno sobre
vectores normalizados y bancos de prototipos por rama/clase.

![Contextualización mediante FAISS](docs/images/faiss-context-en.png)

## Rendimiento experimental

En los conjuntos de prueba usados durante el desarrollo, las seis cabezas
obtuvieron accuracies locales entre 91.76% y 99.31%. Estas cifras describen la
evaluación interna de cada cabeza, no la precisión end-to-end sobre cualquier
distribución externa.

![Rendimiento de los clasificadores](docs/images/classifiers-en.png)

La evaluación también compara Vydra con herramientas establecidas de anotación
de proteínas. Esta figura debe interpretarse junto con el protocolo y alcance de
cada conjunto de datos, porque las herramientas pueden resolver tareas
parcialmente diferentes.

![Comparación con métodos del estado del arte](docs/images/sota-comparison-en.png)

## Estructura del repositorio

```text
Vydra/
├── vydra                         # lanzador de la CLI
├── Vydra_Docker_HF/
│   ├── vydra_cli.py              # comandos y formatos de salida
│   ├── inference_gradio.py       # núcleo de inferencia
│   ├── app.py                    # API FastAPI e interfaz web
│   ├── models/mlp_weights/       # seis cabezas MLP
│   ├── artifacts/                # clases, metadata y bancos descargables
│   └── web/                      # frontend
├── docs/images/                  # figuras del proyecto
├── environment.yml
└── requirements.txt
```

Los datasets originales, embeddings de entrenamiento, notebooks de trabajo y
checkpoints temporales no forman parte de la distribución ligera de GitHub.

## Interfaz web

La aplicación incluida permite cargar FASTA, explorar la ruta jerárquica,
consultar confidencias y contexto biológico, y descargar las predicciones.

![Interfaz web de Vydra](docs/images/web.png)

La misma inferencia puede ejecutarse como aplicación local:

```bash
cd Vydra_Docker_HF
uvicorn app:app --host 0.0.0.0 --port 7860
```

Después abre `http://localhost:7860`.

## Formato de embeddings

La CLI acepta matrices NumPy `(n, 1024)` o diccionarios PyTorch. El formato
anidado usado por el proyecto es:

```python
{
    "class_name": {
        "sequence_id": torch.Tensor(shape=(1024,))
    }
}
```

## Limitaciones

- La calidad depende de la cobertura y distribución de los datos de referencia.
- Una confianza MLP alta no reemplaza una validación biológica independiente.
- La etiqueta de cluster resume vecinos conocidos; no demuestra taxonomía.
- ProstT5 y los bancos de prototipos requieren varios GB de almacenamiento.
- CPU funciona, pero una GPU CUDA reduce considerablemente el tiempo de embedding.

## Documentación

- [Guía detallada de la CLI](Vydra_Docker_HF/CLI.md)
- [Documentación del servicio web](Vydra_Docker_HF/README.md)
- [English version](README.md)

## Cita

Vydra forma parte de un proyecto de tesis en desarrollo. La referencia formal se
añadirá cuando el manuscrito esté disponible. Si utilizas este repositorio antes
de su publicación, enlaza esta página y especifica el commit empleado.
