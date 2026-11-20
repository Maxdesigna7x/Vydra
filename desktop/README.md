# Vydra Desktop

Vydra Desktop abre la interfaz local de Vydra en una ventana de Electron. El
asistente prepara un entorno privado y los archivos de ProstT5. Las entradas y
los resultados se eligen en cada análisis. Usa **Back** para volver del
archivo de texto al informe o **Home** para regresar a la lista de corridas.

**New task** abre las opciones de modelo, entrada, salida y
dispositivo. Desktop ejecuta una corrida a la vez y atiende las tareas
pendientes en el orden en que se añadieron. Las tareas en cola se guardan al
cerrar Vydra y continúan al abrir la misma carpeta de datos. La tarea activa
se detiene al cerrar. Si dejó un checkpoint, puedes reanudarla desde sus
detalles. El botón **Report** abre el resultado de una corrida completada.
La tarjeta activa muestra el tiempo transcurrido, secuencias y chunks
procesados, y durante los embeddings también el lote activo y los chunks
por segundo. La barra y el tiempo restante corresponden a la etapa actual.
La estimación aparece cuando ya se ha medido trabajo nuevo en esa etapa.

| Modo | Debian/Ubuntu x64 | Windows x64 |
| --- | --- | --- |
| CPU | PyTorch y FAISS en CPU | PyTorch y FAISS en CPU |
| NVIDIA | PyTorch y FAISS en CUDA | PyTorch en CUDA, FAISS en CPU |

Cada computadora con NVIDIA debe tener un controlador compatible con CUDA
12.9 en Linux o CUDA 12.6 en Windows. El entorno
de escritorio tiene sus propias dependencias. Para la primera instalación se
necesita conexión y espacio libre en la carpeta seleccionada. Reserva unos
36 GiB para una instalación NVIDIA de Linux, incluido el caché de paquetes. Después de la
preparación se puede ejecutar ProstT5 sin conexión.

Las proteínas que llegan a M4 se clasifican con MLP y FAISS. La tarjeta
completada muestra cuántas predicciones coinciden. En el informe, usa
**Proteins → M4 agreement** para ver únicamente coincidencias o discrepancias
y descargar esa selección. Las dos clases y puntuaciones se guardan en los
resultados por secuencia.

Para conectar un cliente de IA, usa **Vydra → Copy MCP configuration…**.
Selecciona las carpetas de datos que el cliente podrá usar. Las tareas que
envíe aparecerán en la misma cola. Consulta la [guía MCP](../docs/MCP.md).

## Antes de descargar pesos

1. Trabajar en un checkout separado de la rama `desktop/v1`.
   La rama principal sigue siendo la base de la herramienta actual.
2. Desde la raíz, ejecutar `npm --prefix desktop test`. Estas pruebas usan
   archivos pequeños y un servidor de prueba en la misma máquina.
3. El workflow **Vydra Desktop** compila los instaladores al actualizar la rama
   y prueba las dependencias CPU y CUDA en máquinas virtuales sin descargar
   modelos. El job CUDA sin una GPU verifica los paquetes y sus importaciones.
   Una segunda prueba en hardware validará la ejecución CUDA.
4. Revisar o volver a ejecutar en [GitHub Actions](https://github.com/Maxdesigna7x/Vydra/actions/workflows/desktop.yml).
   Los jobs abren el asistente empaquetado sin bajar modelos. Los instaladores
   de prueba están en los artefactos de los jobs de compilación.
   Para compilar manualmente en el sistema objetivo, usar Node 22 y ejecutar
   `npm ci`, `npm run stage` y `npm run make -- --arch=x64` desde `desktop/`.
   Linux requiere `fakeroot` y `dpkg`.

## Validación final y publicación

- Usar un Windows y un Debian/Ubuntu limpios. Validar el instalador, los accesos
  directos y una carpeta con espacios en otro disco. Probar CPU y, en hardware
  NVIDIA, una ejecución pequeña con control de dispositivo en el registro.
  Windows debe indicar PyTorch CUDA y FAISS CPU. Linux debe indicar CUDA en
  ambos. En esta PC esperar a que termine la extracción antes de reservar GPU.
- Completar ProstT5 una vez por carpeta. Interrumpir y reabrir con la misma ruta.
  Confirmar que los parciales y los archivos completos se reutilizan. Desconectar
  la red y ejecutar un análisis pequeño con generación de informe.
- Confirmar la CLI existente con `python -m unittest discover -s tests` desde el
  worktree. Verificar también que la GUI independiente sigue funcionando.
- Tras superar las comprobaciones, crear una etiqueta `desktop-v<versión>`
  que coincida con `desktop/package.json`. El workflow compila, genera
  `SHA256SUMS.txt` y adjunta ambos instaladores a un borrador de GitHub Release.
  Revisar el borrador y publicar los dos juntos. Las etiquetas de Desktop son
  independientes de las etiquetas de artefactos de Vydra.

## Compilar cambios y preparar otra versión

- La ventana de configuración vive en `desktop/setup.html`, `setup.css` y
  `setup.js`. La preparación del entorno vive en `desktop/runtime.cjs` y
  `desktop/desktop_bootstrap.py`. La pantalla de análisis reutiliza
  `vydra_core/gui/`. Los iconos de `desktop/assets/` se derivan de
  `docs/images/vydra-icon.webp`, el logo del README.
- Sube los cambios a una rama con prefijo `desktop/`. Las modificaciones de
  Desktop o del núcleo disparan la compilación de Linux y Windows. En
  **Actions → Vydra Desktop** se pueden descargar ambos instaladores desde
  **Artifacts**. Los pull requests que tocan esos archivos también compilan.
- Cuando quieras distribuir otra versión, actualiza la versión desde
  `desktop/` con `npm version <versión> --no-git-tag-version`, confirma los
  cambios de `package.json` y `package-lock.json` y sube el commit. Añade una
  etiqueta al commit elegido con `git tag desktop-v<versión>` y súbela con
  `git push origin desktop-v<versión>`. GitHub verifica que la etiqueta y el
  paquete coincidan y prepara el borrador con ambos archivos y sus hashes.
- Revisa los resultados antes de publicar. Para una prueba pública usa
  **Set as a pre-release**. La publicación estable queda reservada a versiones
  que superen la validación completa.

## Actualizaciones

Vydra Desktop busca versiones publicadas en GitHub Releases al abrirse y
cada seis horas mientras está abierto. Incluye las versiones de prueba
publicadas que tengan un instalador para el sistema actual. Si encuentra una
versión más nueva, **Download** abre el instalador oficial en el navegador.
También puedes usar **Vydra → Check for updates…**. Sin conexión,
puedes seguir usando tu entorno local y volver a buscar más tarde.

## Progreso de la preparación

El asistente muestra el entorno base, las bibliotecas de Python, los bancos
de referencia, ProstT5, el banco M4 y la comprobación final. Durante una
transferencia, la velocidad y el tiempo restante se calculan con el movimiento
reciente de bytes. Los porcentajes abarcan todo el banco o grupo de archivos
cuando se conoce su tamaño. Para pip se identifica el archivo actual, ya que
pip determina las dependencias y sus tamaños durante la instalación.
Durante la resolución de paquetes, la instalación, la verificación o la
descompresión, se muestra la actividad en curso sin estimar velocidad de red.

## Reanudar una instalación

Pulsa **Pause setup** si necesitas detener la descarga. Vuelve a
elegir la misma carpeta y el mismo modo. Consulta `setup.log` en la
carpeta de datos y el estado de la etapa en `app/<versión-del-entorno>/setup-<modo>.json`.

- Si se interrumpió el entorno, el asistente vuelve a ejecutar su instalación
  y conserva las cachés de paquetes. Las siguientes etapas reutilizan un entorno
  que ya pasó esa parte.
- Si se interrumpió un banco, su archivo `.part` queda en
  `artifacts/artifacts-v1/`. El asistente continúa desde ese tamaño si el
  servidor acepta solicitudes por tramos. Comprueba el tamaño y SHA-256.
- Si se interrumpió ProstT5, se conservan los parciales mantenidos por
  Hugging Face en `models/prostt5-07a6547/`. Los dos bancos y ProstT5 se
  comparten entre los modos de esa misma carpeta.
- El banco FAISS de M4 de ProstT5 (≈710 MiB comprimidos) se descarga una vez.
  Los parciales quedan en `cache/profile-downloads/`. El banco verificado
  queda en `profiles/prostt5/` y se reutiliza al cambiar de versión o modo.
- Si ya tienes estos archivos de las revisiones publicadas, puedes copiarlos
  al directorio correspondiente antes de preparar la app. El asistente verifica
  los bancos, el peso y el tokenizer antes de aceptarlos. Si hay un error
  persistente de integridad en un archivo previamente copiado, aparta ese
  archivo y vuelve a iniciar el asistente.
- Las salidas de investigación y los embeddings previos quedan fuera de las
  carpetas de preparación. Se requiere únicamente un FASTA pequeño para la
  comprobación final.

## Estado del trabajo

- Base de Vydra `76e36d0`. Implementado el lanzador, el asistente, las dos
  configuraciones de dispositivo y el workflow de construcción y borrador.
- La preparación inicial instala ProstT5 con MLP y el banco FAISS de M4. Los perfiles adicionales
  que ya estén en `profiles/` se detectan desde la interfaz. La instalación de
  perfiles opcionales desde la app queda pendiente.
- [Matriz inicial de arranque](https://github.com/Maxdesigna7x/Vydra/actions/runs/44594050844).
  Se generaron ambos instaladores y se importaron las dependencias CPU y CUDA
  de ambos sistemas en una carpeta con espacios. Abrió el asistente instalado
  en Ubuntu y el asistente empaquetado en Windows. Las pruebas no usaron GPU.
- La prueba ligera local inició y cerró el servidor, con el historial en una
  carpeta de NTFS con espacios. También se probaron las descargas parciales y
  las regresiones del núcleo con CUDA oculta.
- Punto de reanudación. Revisar la última ejecución de GitHub Actions. Si la
  compilación y las comprobaciones ligeras están en verde, avanzar a la
  instalación limpia y a las pruebas NVIDIA y offline.
