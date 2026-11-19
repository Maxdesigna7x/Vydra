const { spawn } = require('node:child_process');
const { mkdtemp, readdir, rm } = require('node:fs/promises');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { setTimeout: sleep } = require('node:timers/promises');

async function evaluate(target, expression) {
  const socket = new WebSocket(target);
  try {
    return await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('The setup window did not answer.')), 5_000);
      socket.addEventListener('open', () => socket.send(JSON.stringify({ id: 1, method: 'Runtime.evaluate',
        params: { expression, returnByValue: true } })), { once: true });
      socket.addEventListener('message', event => {
        const message = JSON.parse(event.data);
        if (message.id === 1) {
          clearTimeout(timer);
          if (message.error) reject(new Error(message.error.message));
          else resolve(message.result.result.value);
        }
      });
    });
  } finally {
    socket.close();
  }
}

async function smoke() {
  let executable = process.argv[2];
  if (!executable) {
    const output = path.join(__dirname, 'out');
    const packageFolder = (await readdir(output)).find(name => name.endsWith(`-${process.platform}-x64`));
    if (!packageFolder) throw new Error('No packaged Desktop application found.');
    executable = path.join(output, packageFolder, 'vydra-desktop.exe');
  }
  const isolated = await mkdtemp(path.join(tmpdir(), 'vydra-window-'));
  const args = ['--setup', '--disable-gpu', '--remote-debugging-port=0', `--user-data-dir=${isolated}`];
  const child = spawn(executable, args,
    { stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true });
  let stderr = '';
  let failure;
  child.once('error', error => { failure = error; });
  child.stderr.on('data', chunk => { stderr = (stderr + chunk).slice(-10_000); });
  const closed = new Promise(resolve => child.once('close', resolve));
  try {
    for (let attempt = 0; attempt < 80; attempt += 1) {
      if (failure) throw failure;
      if (child.exitCode !== null) throw new Error(`Vydra exited: ${stderr}`);
      const port = /DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)/u.exec(stderr)?.[1];
      if (port) {
        const pages = await fetch(`http://127.0.0.1:${port}/json/list`).then(response => response.json());
        const page = pages.find(target => target.url.endsWith('/setup.html'));
        if (page) {
          const checks = await evaluate(page.webSocketDebuggerUrl, `({
            title: document.querySelector('h1')?.textContent,
            folder: document.querySelector('#folder')?.value,
            devices: Array.from(document.querySelectorAll('[name=mode]')).map(element => element.value),
            error: document.querySelector('#status')?.textContent
          })`);
          if (checks?.error) throw new Error(checks.error);
          if (checks?.folder && checks.title === 'Configurar Vydra' && checks.devices.join(',') === 'cuda,cpu') {
            console.log('Packaged setup window opened with a default folder and both device choices.');
            return;
          }
        }
      }
      await sleep(250);
    }
    throw new Error(`The setup window did not initialize: ${stderr}`);
  } finally {
    child.kill();
    await closed;
    await rm(isolated, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
  }
}

smoke().catch(error => { console.error(error); process.exitCode = 1; });
