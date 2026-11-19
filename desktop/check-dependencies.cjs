const { prepare } = require('./runtime.cjs');
const path = require('node:path');

const [root, mode] = process.argv.slice(2);
if (!root || !['cuda', 'cpu'].includes(mode)) {
  throw new Error('Usage: node check-dependencies.cjs DATA_DIR cpu|cuda');
}
prepare(path.resolve(root), mode, path.join(__dirname, 'resources'), text => process.stdout.write(text),
  { dependenciesOnly: true }).catch(error => { console.error(error); process.exitCode = 1; });
