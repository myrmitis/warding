import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
const read = url => execFileSync('curl', ['-4', '--fail', '--location', '--silent', '--show-error', '--max-time', '30', String(url)], { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });

const base = process.argv[2];
assert(base, 'Pass the running website URL');
const pages = ['/', '/source/', '/quickstart/', '/about/', '/changelog/', '/verified/', '/registry/', '/security/', '/channels/slack/', '/channels/telegram/', '/guides/write-a-policy/', '/guides/run-claude-code-24-7/'];
for (const path of pages) {
  const html = read(new URL(path, base));
  const { text: visible, assets, links } = JSON.parse(execFileSync('python3', [fileURLToPath(new URL('./read-page.py', import.meta.url))], { input: html, encoding: 'utf8' }));
  assert(!/source publication (?:is )?pending|source access is not publicly available|repository is not publicly accessible/i.test(visible), path);
  if (['/', '/source/', '/quickstart/'].includes(path)) assert(/local beta/i.test(visible), path);
  const predecessor = 'junc' + 'tion';
  assert(!visible.includes('~/.' + predecessor) && !visible.includes(predecessor.toUpperCase() + '_OWNER_ID'), 'Retired configuration instructions: ' + path);
  assert(!/silent alias/i.test(visible), 'Unsupported CLI alias: ' + path);
  if (path === '/source/') assert(links.includes('https://github.com/myrmitis/warding'), 'Public source link');
  if (path === '/') {
    assert(/UI concept|Example data/.test(visible), 'Demo disclosure');
    assert(/overnight runs are not yet runtime-verified/.test(visible), 'Overnight limit');
  }
  if (path === '/quickstart/') {
    assert(/clean install and live end-to-end workflow have not yet been verified/.test(visible), 'Installation limit');
    assert(/No signed installers yet/.test(visible), 'Installer limit');
  }
  for (const url of assets) {
    read(new URL(url, base));
  }
  console.log(`PASS ${new URL(path, base)}`);
}
