# Vydra como servidor MCP local

En Desktop, abre **Vydra → Copy MCP configuration…** y elige las
carpetas que contienen tus entradas y donde guardarás las salidas. Agrega
el servidor `vydra` a la configuración del cliente MCP usando el JSON
copiado. Si el cliente ya tiene otros servidores, incorpora la entrada
`vydra` a los existentes. Mantén Desktop abierto para que las tareas
continúen. Sus corridas y las del cliente figuran en la misma cola.

## Instalación con Python

Usa la rama `desktop/v1` con el [entorno y los perfiles instalados](MODEL_PROFILES.md).
La configuración de un cliente que usa el formato `mcpServers` puede ser así:

```json
{
  "mcpServers": {
    "vydra": {
      "command": "/ruta/al/entorno/bin/python",
      "args": [
        "/ruta/al/repositorio/vydra", "mcp",
        "--root", "/ruta/a/entradas",
        "--root", "/ruta/a/resultados"
      ]
    }
  }
}
```

Cambia las rutas por las de tu equipo. En Windows, usa el ejecutable `python.exe`
del entorno. Las carpetas indicadas con `--root` deben existir. Opcionalmente,
usa `--state-dir` para elegir dónde se guarda el historial. Si ya está activa
la interfaz web de Python, el servidor MCP se conecta a ella cuando ambos
usan el mismo directorio de historial. Cuando MCP administra la cola por sí
solo, cerrar el cliente interrumpe la corrida activa y conserva el historial,
la cola pendiente y los checkpoints ya escritos.

| Herramienta | Qué hace |
| --- | --- |
| `submit_run` | Añade un FASTA o una carpeta a la cola y devuelve `run_id`. Puedes indicar modelo, dispositivo y tamaño de lote. |
| `get_run_status` | Consulta etapa, tiempo transcurrido, secuencias, chunks, velocidad y estimación de la etapa cuando está disponible. |
| `get_run_result` | Devuelve rutas a los archivos generados y conteos de acuerdo de M4 cuando termina la corrida. |

El cliente envía rutas y Vydra analiza los archivos localmente con los
perfiles instalados. El servicio MCP usa entrada y salida estándar
(`stdio`). Solo acepta entradas y salidas dentro de las carpetas autorizadas.
