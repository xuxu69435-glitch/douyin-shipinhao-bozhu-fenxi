import { chromium } from 'playwright-core';
import { pathToFileURL } from 'node:url';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export function runtimeStatus() {
  const roots = [process.env.PROGRAMFILES, process.env['ProgramFiles(x86)']].filter(Boolean);
  const version = JSON.parse(readFileSync(new URL('./node_modules/playwright-core/package.json', import.meta.url), 'utf8')).version;
  return { playwright: version, edge_available: roots.some(root => existsSync(join(root, 'Microsoft/Edge/Application/msedge.exe'))) };
}

export function targetUrl(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.hostname !== 'www.douyin.com' || url.port || url.username || url.password ||
      !/^\/(video\/\d{8,25}|user\/MS4w[\w.-]+)\/?$/.test(url.pathname)) throw new Error('invalid_target');
  return new URL(url.pathname, url.origin);
}

export function importedCookies(text = '') {
  return text.split(';').map(part => part.trim()).filter(Boolean).map(part => {
    const index = part.indexOf('=');
    return { name: index < 0 ? '' : part.slice(0, index), value: index < 0 ? part : part.slice(index + 1),
      url: 'https://www.douyin.com/', secure: true, sameSite: 'Lax' };
  });
}

export function material(raw) {
  if (!raw || !/^\d{8,25}$/.test(String(raw.aweme_id ?? '')) || !raw.author?.sec_uid) return null;
  return { aweme_id: String(raw.aweme_id), desc: String(raw.desc ?? ''), create_time: raw.create_time,
    author: { sec_uid: String(raw.author.sec_uid), nickname: String(raw.author.nickname ?? '') },
    video: { play_addr: { url_list: (raw.video?.play_addr?.url_list ?? []).filter(url => typeof url === 'string' && url.startsWith('https://')) } } };
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

export async function collect(input, emit = () => {}) {
  const target = targetUrl(input.url);
  const profile = target.pathname.startsWith('/user/');
  const platformId = target.pathname.split('/')[2];
  const limit = input.limit === 30 ? 30 : 10;
  const deadline = Date.now() + Math.min(120000, Math.max(15000, input.timeout_ms ?? 90000));
  const browser = await chromium.launch({ channel: 'msedge', headless: false });
  const pages = [];
  let detail = null;
  const pending = new Set();
  let denied = false;
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 850 } });
    if (input.cookie) await context.addCookies(importedCookies(input.cookie));
    const page = await context.newPage();
    const observe = async response => {
      const url = new URL(response.url());
      if (url.origin !== 'https://www.douyin.com') return;
      const isPost = url.pathname.includes('/aweme/post/');
      const isDetail = url.pathname.includes('/aweme/detail/');
      if (!isPost && !isDetail) return;
      if (profile && isPost && uniqueWorks().length >= limit) return; // Ignore normal browser prefetch beyond the selected sample.
      if (response.status() === 403 || response.status() === 401 || response.status() === 429) {
        denied = true;
        emit({ event: 'browser_request_denied', status: response.status() });
        return;
      }
      if (response.status() !== 200) return;
      let body;
      try { body = await response.json(); } catch { return; }
      if (isDetail && String(body.aweme_detail?.aweme_id) === platformId) detail = material(body.aweme_detail);
      if (profile && isPost && url.searchParams.get('sec_user_id') === platformId && Array.isArray(body.aweme_list)) {
        if (uniqueWorks().length >= limit) return;
        const cursor = url.searchParams.get('max_cursor') ?? '0';
        if (pages.some(p => p.request_cursor === cursor)) return;
        const seen = new Set(uniqueWorks().map(v => v.aweme_id));
        const remaining = limit - seen.size;
        const items = body.aweme_list.map(material).filter(v => v && v.author.sec_uid === platformId && !seen.has(v.aweme_id));
        pages.push({ request_cursor: cursor, has_more: body.has_more, max_cursor: body.max_cursor,
          aweme_list: items.slice(0, remaining) });
        emit({ event: 'browser_page_observed', pages: pages.length, unique: uniqueWorks().length });
      }
    };
    const uniqueWorks = () => [...new Map(pages.flatMap(p => p.aweme_list).map(v => [v.aweme_id, v])).values()];
    page.on('response', response => {
      const task = observe(response).catch(() => {});
      pending.add(task); task.finally(() => pending.delete(task));
    });
    emit({ event: 'browser_opened', login_or_verification_by_user: true });
    await page.goto(target.href, { waitUntil: 'domcontentloaded', timeout: 30000 });
    let scrolls = 0;
    while (Date.now() < deadline) {
      if (!profile && detail) break;
      if (profile && (uniqueWorks().length >= limit || (pages.length && pages.at(-1).has_more === 0))) break;
      if (page.isClosed()) throw new Error('browser_closed_by_user');
      if (profile && pages.length && scrolls < 20) {
        await page.mouse.move(960, 700);
        await page.mouse.wheel(0, 1500);
        scrolls++;
      }
      await delay(1500);
    }
    let settleTimer;
    await Promise.race([Promise.allSettled([...pending]), new Promise(resolve => { settleTimer = setTimeout(resolve, 5000); })]);
    clearTimeout(settleTimer);
    if (!profile && !detail) throw new Error(denied ? 'browser_platform_denied' : 'browser_detail_not_observed');
    if (profile && !pages.length) throw new Error(denied ? 'browser_platform_denied' : 'browser_posts_not_observed');
    return { kind: profile ? 'profile' : 'video', detail, pages,
      stop_reason: profile ? (uniqueWorks().length >= limit ? 'limit_reached' : pages.at(-1).has_more === 0 ? 'end_of_list' : 'browser_page_timeout') : 'single_video' };
  } finally {
    await browser.close();
  }
}

async function main() {
  let input = '';
  for await (const chunk of process.stdin) {
    input += chunk;
    if (Buffer.byteLength(input) > 131072) throw new Error('input_too_large');
  }
  try {
    const payload = JSON.parse(input);
    if (payload.op === 'status') {
      process.stdout.write(JSON.stringify({ ok: true, result: runtimeStatus() }) + '\n');
      return;
    }
    const result = await collect(payload, value => process.stdout.write(JSON.stringify(value) + '\n'));
    process.stdout.write(JSON.stringify({ ok: true, result }) + '\n');
  } catch (error) {
    const allowed = ['invalid_target', 'browser_closed_by_user', 'browser_platform_denied', 'browser_detail_not_observed', 'browser_posts_not_observed'];
    process.stdout.write(JSON.stringify({ ok: false, error: allowed.includes(error.message) ? error.message : 'browser_runtime_failed' }) + '\n');
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
