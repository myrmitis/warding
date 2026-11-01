import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
const read = url => execFileSync('curl', ['-4', '--fail', '--location', '--silent', '--show-error', '--max-time', '30', String(url)], { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024 });

const base = process.argv[2];
assert(base, 'Pass the running website URL');
const pages = ['/', '/source/', '/quickstart/'];
for (const path of pages) {
  const html = read(new URL(path, base));
  const visible = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '').replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '').replace(/<[^>]*>/g, ' ');
  assert(!/source publication (?:is )?pending|source access is not publicly available|repository is not publicly accessible/i.test(visible), path);
  assert(/local beta/i.test(visible), path);
  if (path === '/source/') assert(html.includes('href="https://github.com/myrmitis/warding"'), 'Public source link');
  if (path === '/') {
    assert(/UI concept|Example data/.test(visible), 'Demo disclosure');
    assert(/overnight runs are not yet runtime-verified/.test(visible), 'Overnight limit');
  }
  if (path === '/quickstart/') {
    assert(/clean install and live end-to-end workflow have not yet been verified/.test(visible), 'Installation limit');
    assert(/No signed installers yet/.test(visible), 'Installer limit');
  }
  for (const url of new Set([...html.matchAll(/(?:src|href)="(\/_astro\/[^"#]+)"/g)].map(x => x[1]))) {
    read(new URL(url, base));
  }
  console.log(`PASS ${new URL(path, base)}`);
}
