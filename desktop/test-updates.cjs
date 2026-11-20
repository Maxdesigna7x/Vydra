const assert = require('node:assert/strict');
const test = require('node:test');
const { checkForUpdate } = require('./updates.cjs');

const official = 'https://github.com/Maxdesigna7x/Vydra/releases/download';
const release = (version, options = {}) => {
  const tag = `desktop-v${version}`;
  const files = [`vydra-desktop_${version}_amd64.deb`, 'Vydra-Setup-x64.exe'];
  return {
    draft: false, prerelease: true, tag_name: tag,
    assets: files.map(name => ({ name, state: 'uploaded', browser_download_url: `${official}/${tag}/${name}` })),
    ...options,
  };
};
const lookup = (releases, platform = 'linux', version = '0.2.2') => checkForUpdate({
  version, platform, arch: 'x64',
  fetch: async () => ({ ok: true, json: async () => releases }),
});

test('chooses the newest numerically higher Desktop version with an installer per platform', async () => {
  const incomplete = release('0.12.0');
  incomplete.assets.pop();
  const releases = [
    release('0.3.0'), release('0.11.0'), release('0.2.10'),
    release('0.13.0', { draft: true }), incomplete,
    release('8.0.0', { tag_name: 'model-profiles-m4-v1' }),
  ];
  assert.deepEqual(await lookup(releases, 'linux'), {
    version: '0.12.0', prerelease: true, url: `${official}/desktop-v0.12.0/vydra-desktop_0.12.0_amd64.deb`,
  });
  assert.deepEqual(await lookup(releases, 'win32'), {
    version: '0.11.0', prerelease: true, url: `${official}/desktop-v0.11.0/Vydra-Setup-x64.exe`,
  });
});

test('ignores untrusted asset URLs and malformed, current or older versions', async () => {
  const changed = release('0.4.0');
  changed.assets[0].browser_download_url = 'https://example.net/installer.deb';
  const pending = release('0.4.1');
  pending.assets[0].state = 'new';
  assert.equal(await lookup([changed, pending, release('0.2.2'), release('0.1.9'), release('0.90.fake')]), null);
});

test('keeps unsupported platforms and architectures offline', async () => {
  for (const [platform, arch] of [['darwin', 'x64'], ['linux', 'arm64']]) {
    assert.equal(await checkForUpdate({ version: '0.2.2', platform, arch,
      fetch: async () => { assert.fail('Unexpected network request'); },
    }), null);
  }
});

test('surfaces an unavailable release service for the caller to handle', async () => {
  await assert.rejects(checkForUpdate({
    version: '0.2.2', platform: 'linux', arch: 'x64',
    fetch: async () => ({ ok: false, status: 503 }),
  }), /HTTP 503/u);
});
