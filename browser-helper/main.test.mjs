import assert from 'node:assert/strict';
import test from 'node:test';
import { targetUrl, importedCookies, material } from './main.mjs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

test('status entry point loads packaged modules without opening a browser', () => {
  const answer = spawnSync(process.execPath, [fileURLToPath(new URL('./main.mjs', import.meta.url))],
    { input: '{"op":"status"}', encoding: 'utf8' });
  assert.equal(answer.status, 0);
  const status = JSON.parse(answer.stdout);
  assert.equal(status.ok, true);
  assert.equal(status.result.playwright, '1.65.0');
  assert.equal(typeof status.result.edge_available, 'boolean');
});

test('canonical targets keep authentication off other sites', () => {
  assert.equal(targetUrl('https://www.douyin.com/video/7699679130752748809?tracking=fixture').href,
    'https://www.douyin.com/video/7699679130752748809');
  for (const value of ['http://www.douyin.com/video/7699679130752748809',
    'https://www.douyin.com.evil.invalid/video/7699679130752748809', 'https://user:pass@www.douyin.com/user/MS4wfixture']) {
    assert.throws(() => targetUrl(value));
  }
});

test('only manually supplied cookies are mapped to the target host', () => {
  const items = importedCookies('sessionid=fixture==; nameless-fixture; prefs={"v":1}');
  assert.equal(items[0].value, 'fixture==');
  assert.equal(items[1].name, '');
  assert.equal(items[1].value, 'nameless-fixture');
  assert.ok(items.every(item => item.url === 'https://www.douyin.com/' && item.secure));
});

test('only required public material crosses the private bridge', () => {
  const item = material({ aweme_id: '7699679130752748809', desc: 'fixture', author: {sec_uid:'MS4wfixture'},
    viewer_private_field:'must-not-forward', video: {play_addr:{url_list:['https://v1.douyinvod.com/fixture','file:///forbidden']}} });
  assert.equal(item.viewer_private_field, undefined);
  assert.equal(item.video.play_addr.url_list.length, 1);
  assert.equal(material({aweme_id:'not-a-video'}), null);
});
