// Run with VYDRA_PLAYWRIGHT_PACKAGE and optionally VYDRA_CHROMIUM_EXECUTABLE.
// The report fixture must be passed as argv[2]; no network or inference needed.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.VYDRA_PLAYWRIGHT_PACKAGE || 'playwright');

(async () => {
  const browser = await chromium.launch({headless: true,
    executablePath: process.env.VYDRA_CHROMIUM_EXECUTABLE || undefined,
    args: ['--no-sandbox']});
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'vydra-browser-'));
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1100}, acceptDownloads: true});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
    assert.match(await page.locator('[data-el="table-count"]').textContent(), /12 proteins/);
    assert.match(await page.locator('[data-el="timing"]').textContent(), /total processing: 3 s/);
    // Neighbor metadata is explicit and the legacy nearest ID is recovered.
    await page.locator('[data-id="fixture_0"]').click();
    const detail = await page.locator('[data-el="detail"]').textContent();
    assert.match(detail, /ref0/);
    assert.match(detail, /No specific function in this annotation/);
    assert.match(detail, /4\/4 annotated neighbors share ExampleGenus; 4\/5/);
    assert.match(detail, /Assigned cluster context/);
    // Combine structural class, reference genus and reference family.
    for (const [field, value] of [['prediction', 'Collar'], ['genus', 'ExampleGenus'], ['family', 'ExampleFamily']]) {
      await page.locator(`[data-filter-button="${field}"]`).click();
      await page.locator(`[data-filter="${field}"]`).selectOption({label: value});
    }
    await page.locator('[data-el="table-mode"]').selectOption('pages');
    assert.match(await page.locator('[data-el="table-count"]').textContent(), /8 proteins.*1–6 shown/);
    assert.equal(await page.locator('[data-el="proteins"] tr').count(), 6);
    const [fastaDownload] = await Promise.all([
      page.waitForEvent('download'), page.locator('[data-el="download-fasta"]').click()]);
    const fastaFile = path.join(temporary, 'selected.faa');
    await fastaDownload.saveAs(fastaFile);
    const fasta = await fs.readFile(fastaFile, 'utf8');
    assert.equal((fasta.match(/^>/gm) || []).length, 8);
    assert.match(fasta, />duplicate \|original annotation 0\| country=Mexico \|\nMeKLL\*/);
    assert.match(fasta, />duplicate \|original annotation 1\|/);
    assert.doesNotMatch(fasta, /fixture_8|fixture_10/);
    const [csvDownload] = await Promise.all([
      page.waitForEvent('download'), page.locator('[data-el="download"]').click()]);
    const csvFile = path.join(temporary, 'selected.csv');
    await csvDownload.saveAs(csvFile);
    const csv = await fs.readFile(csvFile, 'utf8');
    assert.equal(csv.trim().split('\n').length, 9);
    assert.match(csv, /nearest|neighbors/);
    assert.match(csv, /original_header/);
    // Eukaryotic class metadata remains available without neighbor retrieval.
    await page.locator('[data-el="clear-filters"]').click();
    await page.locator('[data-el="table-mode"]').selectOption('scroll');
    await page.locator('[data-id="fixture_10"]').click();
    assert.match(await page.locator('[data-el="detail"]').textContent(), /Published function categoryHypothetical/);
    assert.match(await page.locator('[data-el="detail"]').textContent(), /no FAISS retrieval/);
    // A copied standalone HTML still exports original residues offline.
    const copied = path.join(temporary, 'standalone.html');
    await fs.copyFile(process.argv[2], copied);
    await page.goto(pathToFileURL(copied).href);
    assert.equal(await page.locator('[data-el="download-fasta"]').isEnabled(), true);
    assert.deepEqual(errors, []);
    await page.screenshot({path: path.join(path.dirname(process.argv[2]), 'preview.png'), fullPage: true});
    console.log('PASS: UI filters, class metadata, 8-row FASTA across pages, duplicate headers, original residues, CSV and portable HTML');
  } finally {
    await browser.close();
    await fs.rm(temporary, {recursive: true, force: true});
  }
})().catch(error => {console.error(error); process.exit(1)});
