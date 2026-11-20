const { ipcRenderer } = require('electron');

window.addEventListener('DOMContentLoaded', () => {
  const toolbar = document.createElement('vydra-navigation');
  const shadow = toolbar.attachShadow({ mode: 'open' });
  shadow.innerHTML = `
    <style>
      :host { display: inline-flex; align-items: center; color: inherit; }
      :host(.corner) { float: right; position: sticky; top: 8px; z-index: 10000;
        margin: 0 8px 4px 12px; padding: 2px; border-radius: 8px; background: Canvas; color: CanvasText; }
      nav { display: flex; gap: 2px; }
      button { display: grid; place-items: center; width: 32px; height: 32px; padding: 0;
        border: 0; border-radius: 6px; background: transparent; color: inherit; opacity: .78; }
      button:enabled { cursor: pointer; }
      button:enabled:hover { background: color-mix(in srgb, currentColor 10%, transparent); opacity: 1; }
      button:disabled { opacity: .32; }
      button:focus-visible { outline: 2px solid Highlight; outline-offset: 1px; }
      svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.75;
        stroke-linecap: round; stroke-linejoin: round; }
    </style>
    <nav aria-label="Vydra navigation">
      <button id="back" type="button" aria-label="Back" title="Back" disabled>
        <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m12 5-7 7 7 7M5 12h14"/></svg>
      </button>
      <button id="home" type="button" aria-label="Home" title="Home" disabled>
        <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m3 10 9-7 9 7M5 9v11h5v-6h4v6h5V9"/></svg>
      </button>
    </nav>
  `;
  const back = shadow.getElementById('back');
  const home = shadow.getElementById('home');

  back.addEventListener('click', () => ipcRenderer.send('navigation:back'));
  home.addEventListener('click', () => ipcRenderer.send('navigation:home'));
  ipcRenderer.on('navigation:state', (_event, { canGoBack, atHome }) => {
    back.disabled = !canGoBack;
    home.disabled = atHome;
  });
  const actions = document.querySelector('main > header .header-actions, .page-header .theme-row');
  if (actions) actions.append(toolbar);
  else {
    toolbar.classList.add('corner');
    document.body.prepend(toolbar);
  }
  ipcRenderer.send('navigation:ready');

  const header = document.querySelector('main > header .header-actions');
  if (window.location.pathname !== '/' || !header) return;

  const notice = document.createElement('span');
  notice.hidden = true;
  notice.setAttribute('aria-live', 'polite');
  const download = document.createElement('button');
  download.type = 'button';
  download.className = 'button quiet';
  download.addEventListener('click', () => ipcRenderer.send('updates:download'));
  notice.append(download);
  header.prepend(notice);

  ipcRenderer.on('updates:available', (_event, update) => {
    notice.hidden = !update;
    if (!update) return;
    download.textContent = `Download v${update.version}`;
    download.title = update.prerelease ? 'Download preview from GitHub' : 'Download update from GitHub';
  });
  ipcRenderer.send('updates:ready');
});
