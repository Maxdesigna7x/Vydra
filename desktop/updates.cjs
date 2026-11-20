const repository = 'Maxdesigna7x/Vydra';
const releasesAPI = `https://api.github.com/repos/${repository}/releases?per_page=100`;
const releaseDownload = `https://github.com/${repository}/releases/download`;
const versionPattern = /^(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})\.(0|[1-9]\d{0,8})$/u;

function parseVersion(version) {
  return typeof version === 'string' ? version.match(versionPattern)?.slice(1).map(Number) : null;
}

function compareVersions(a, b) {
  for (let index = 0; index < a.length; index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return 0;
}

async function checkForUpdate({ version, platform, arch, fetch }) {
  const current = parseVersion(version);
  if (!current || arch !== 'x64' || !['linux', 'win32'].includes(platform)) return null;

  const response = await fetch(releasesAPI, {
    headers: { Accept: 'application/vnd.github+json' },
    redirect: 'error',
    cache: 'no-cache',
    signal: AbortSignal.timeout(12_000),
  });
  if (!response.ok) throw new Error(`GitHub returned HTTP ${response.status}`);
  const releases = await response.json();
  if (!Array.isArray(releases)) throw new Error('Invalid GitHub releases response');

  let latest = null;
  let latestVersion = current;
  for (const release of releases) {
    const tag = release?.tag_name;
    if (release?.draft !== false || typeof tag !== 'string' || !tag.startsWith('desktop-v')) continue;
    const candidate = tag.slice('desktop-v'.length);
    const parsed = parseVersion(candidate);
    if (!parsed || compareVersions(parsed, latestVersion) <= 0) continue;
    const filename = platform === 'linux' ? `vydra-desktop_${candidate}_amd64.deb` : 'Vydra-Setup-x64.exe';
    const url = `${releaseDownload}/${tag}/${filename}`;
    if (!Array.isArray(release.assets) || !release.assets.some(asset =>
      asset?.name === filename && asset.state === 'uploaded' && asset.browser_download_url === url)) continue;

    latest = { version: candidate, prerelease: release.prerelease === true, url };
    latestVersion = parsed;
  }
  return latest;
}

module.exports = { checkForUpdate };
