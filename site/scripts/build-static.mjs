import { createHash } from 'node:crypto';
import { copyFile, lstat, mkdir, readFile, readdir, rm } from 'node:fs/promises';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = join(root, 'static');
const output = join(root, 'dist');
const manifest = JSON.parse(await readFile(join(root, 'static-manifest.json'), 'utf8'));
const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');

async function files(directory) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Static export contains a symlink: ${path}`);
    if (entry.isDirectory()) result.push(...await files(path));
    else if (entry.isFile()) result.push(path);
    else throw new Error(`Static export contains a special file: ${path}`);
  }
  return result.sort();
}

if (manifest.schema !== 1) throw new Error('Unsupported static manifest schema');
const found = (await files(source)).map((file) => relative(source, file).split(sep).join('/')).sort();
const expected = manifest.outputs.map((row) => row.file).sort();
if (JSON.stringify(found) !== JSON.stringify(expected)) throw new Error('Static export file inventory differs from reviewed manifest');

for (const row of manifest.authoring_inputs) {
  if (!/^(src\/|public\/|(?:astro\.config\.mjs|authoring-tsconfig\.json)$|\.\.\/(NOTICE|LICENSE|CHANGELOG\.md)$)/.test(row.file)) throw new Error(`Unapproved authoring input: ${row.file}`);
  const path = resolve(root, row.file);
  if (!(await lstat(path)).isFile() || digest(await readFile(path)) !== row.sha256) throw new Error(`Authoring input changed: ${row.file}. Review a fresh export before publishing.`);
}
const authoring = [...await files(join(root, 'src')), ...await files(join(root, 'public'))].map((file) => relative(root, file).split(sep).join('/')).sort();
const recorded = manifest.authoring_inputs.filter((row) => /^(src|public)\//.test(row.file)).map((row) => row.file).sort();
if (JSON.stringify(authoring) !== JSON.stringify(recorded)) throw new Error('Authoring file inventory changed. Review a fresh export before publishing.');

for (const row of manifest.outputs) {
  const path = resolve(source, row.file);
  if (!path.startsWith(source + sep)) throw new Error(`Invalid export path: ${row.file}`);
  const bytes = await readFile(path);
  if (bytes.length !== row.size || digest(bytes) !== row.sha256) throw new Error(`Static bytes differ from reviewed manifest: ${row.file}`);
}

await rm(output, { recursive: true, force: true });
for (const row of manifest.outputs) {
  const target = resolve(output, row.file);
  await mkdir(dirname(target), { recursive: true });
  await copyFile(resolve(source, row.file), target);
}
console.log(`Verified and built ${manifest.outputs.length} static files from reviewed source tree ${manifest.source_tree}.`);
