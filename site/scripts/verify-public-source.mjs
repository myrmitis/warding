import assert from 'node:assert/strict';

const base = process.argv[2];
assert(base, 'Pass the running website URL');
const pages = ['/', '/source/', '/quickstart/'];
for (const path of pages) {
  const response = await fetch(new URL(path, base));
  assert.equal(response.status, 200, path);
  const html = await response.text();
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
    assert.equal((await fetch(new URL(url, base))).status, 200, url);
  }
  console.log(`PASS ${new URL(path, base)}`);
}
