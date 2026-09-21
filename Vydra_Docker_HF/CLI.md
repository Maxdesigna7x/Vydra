# Vydra CLI

La CLI ejecuta localmente la cascada de seis modelos MLP y la asignacion de
clusters con los artefactos incluidos en esta carpeta. No necesita el servidor
web ni una API externa.

## Comprobar la instalacion

Desde la raiz del proyecto:

```bash
conda run -n vydra ./vydra doctor
```

## Clasificar secuencias

```bash
conda run -n vydra ./vydra predict --seq "MSTNPKPQR..."
conda run -n vydra ./vydra predict --fasta muestras.fasta
cat muestras.fasta | conda run -n vydra ./vydra predict --stdin
```

Los formatos disponibles son `table`, `json`, `jsonl` y `csv`:

```bash
conda run -n vydra ./vydra predict --fasta muestras.fasta \
  --format csv --output predicciones.csv
```

## Inferencia completamente offline

Los pesos MLP y la metadata viven dentro de `Vydra_Docker_HF/`. En una copia
obtenida desde GitHub, descarga los bancos de prototipos publicados en Releases:

```bash
conda run -n vydra ./vydra download-artifacts
```

Para secuencias crudas tambien se necesita ProstT5. Se puede guardar una copia
en el bundle una sola vez:

```bash
conda run -n vydra ./vydra download-model
```

Despues se puede impedir cualquier acceso a la red:

```bash
conda run -n vydra ./vydra predict --offline --fasta muestras.fasta
```

Tambien se puede apuntar a una copia local existente:

```bash
export VYDRA_PROSTT5_PATH=/ruta/a/ProstT5
conda run -n vydra ./vydra predict --offline --fasta muestras.fasta
```

Si ya se tienen embeddings ProstT5 de 1024 dimensiones, no es necesario cargar
el modelo base:

```bash
conda run -n vydra ./vydra predict --embedding embeddings.npy --format json
```

Por defecto se usa CUDA cuando PyTorch la detecta y CPU en caso contrario. Se
puede forzar con `--device cpu` o `--device cuda`.
