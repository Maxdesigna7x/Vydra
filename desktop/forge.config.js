const path = require('node:path');

const icon = path.join(__dirname, 'assets', 'vydra');

module.exports = {
  packagerConfig: {
    asar: true,
    icon,
    executableName: 'vydra-desktop',
    extraResource: [path.join(__dirname, 'resources')],
    ignore: [/^\/resources(?:\/|$)/, /^\/test_/],
  },
  makers: [
    {
      name: '@electron-forge/maker-deb',
      config: { options: { maintainer: 'Maxdesigna7x', icon: `${icon}.png` } },
    },
    {
      name: '@electron-forge/maker-squirrel',
      config: {
        name: 'vydra_desktop',
        setupExe: 'Vydra-Setup-x64.exe',
        setupIcon: `${icon}.ico`,
        iconUrl: 'https://raw.githubusercontent.com/Maxdesigna7x/Vydra/refs/heads/desktop/v1/desktop/assets/vydra.ico',
      },
    },
  ],
};
