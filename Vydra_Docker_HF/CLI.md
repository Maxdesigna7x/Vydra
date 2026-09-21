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

## Batch automatico y memoria

Por defecto Vydra ordena los chunks por longitud real, crea buckets de 128 aa y
calcula el batch usando la VRAM o RAM libre despues de cargar ProstT5. La
politica GPU usa margenes conservadores calibrados con una RTX 3060 de 11.63
GiB: 128 aa fue estable hasta batch 256 y 512 aa hasta batch 32; los primeros
OOM aparecieron en 512 y 64 respectivamente. Los defaults se mantienen por
debajo de esos limites y se escalan para el dispositivo detectado.

Si una estimacion aun resulta demasiado alta por fragmentacion o por otro
proceso, Vydra captura el error de memoria, reduce el batch a la mitad y reintenta
sin perder secuencias ni alterar el orden final.

Opciones disponibles:

```text
--batch-size N          Fuerza el batch inicial (el fallback OOM sigue activo)
--max-batch-size N      Limite superior del calculo automatico
--memory-fraction F     Fraccion maxima de memoria total: GPU 0.85, CPU 0.75
--reserve-memory-gb G   Reserva explicita que Vydra no debe utilizar
--length-bin N          Ancho de los buckets de longitud; default 128 aa
```

Ejemplo conservador para compartir una GPU con otro proceso:

```bash
./vydra predict --fasta muestras.fasta \
  --memory-fraction 0.70 --reserve-memory-gb 2 --max-batch-size 64
```

La aplicacion web usa la misma politica. En despliegues se puede configurar con
`VYDRA_BATCH_SIZE`, `VYDRA_MAX_BATCH_SIZE`, `VYDRA_MEMORY_FRACTION`,
`VYDRA_RESERVE_MEMORY_GB` y `VYDRA_LENGTH_BIN`.
