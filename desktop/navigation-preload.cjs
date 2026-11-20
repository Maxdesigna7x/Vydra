const { ipcRenderer } = require('electron');

window.addEventListener('DOMContentLoaded', () => {
  const toolbar = document.createElement('vydra-navigation');
  Object.assign(toolbar.style, { display: 'block', position: 'sticky', top: '0', zIndex: '10000' });
  const shadow = toolbar.attachShadow({ mode: 'open' });
  shadow.innerHTML = `
    <style>
      :host { color-scheme: light dark; font: 14px system-ui, sans-serif; background: Canvas; }
      nav { box-sizing: border-box; display: flex; align-items: center; gap: 8px; height: 52px;
        padding: 0 16px; border-bottom: 1px solid color-mix(in srgb, CanvasText 24%, Canvas); }
      button { font: inherit; min-height: 34px; padding: 0 12px; border-radius: 6px;
        border: 1px solid color-mix(in srgb, CanvasText 34%, Canvas); background: ButtonFace; color: ButtonText; }
      button:enabled { cursor: pointer; }
      button:enabled:hover { background: color-mix(in srgb, ButtonFace 88%, ButtonText); }
      button:disabled { opacity: 0.48; }
      button:focus-visible { outline: 2px solid Highlight; outline-offset: 2px; }
    </style>
    <nav aria-label="Navegación de Vydra">
      <button id="back" type="button" disabled><span aria-hidden="true">←</span> Atrás</button>
      <button id="home" type="button" disabled>Inicio</button>
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
  document.body.prepend(toolbar);
  ipcRenderer.send('navigation:ready');
});
