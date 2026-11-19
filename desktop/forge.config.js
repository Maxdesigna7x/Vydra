const path = require('node:path');

module.exports = {
  packagerConfig: {
    asar: true,
    executableName: 'vydra-desktop',
    extraResource: [path.join(__dirname, 'resources')],
    ignore: [/^\/resources(?:\/|$)/, /^\/test_/],
  },
  makers: [
    { name: '@electron-forge/maker-deb', config: { options: { maintainer: 'Maxdesigna7x' } } },
    { name: '@electron-forge/maker-squirrel', config: { name: 'vydra_desktop', setupExe: 'Vydra-Setup-x64.exe' } },
  ],
};
