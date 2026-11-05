// Browser acceptance in a disposable HOME. No npm dependencies or desktop changes.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp, mkdir, readFile, writeFile, chmod, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const repo = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const root = await mkdtemp(path.join(tmpdir(), 'desktop-theming-browser-'));
const output = process.env.SCREENSHOT_DIR || path.join(root, 'screenshots');
let application, chromium, socket;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, label) {
  for (let i = 0; i < 100; i++) {
    const value = await check();
    if (value) return value;
    await pause(100);
  }
  throw new Error(`Timed out: ${label}`);
}

try {
  await mkdir(path.join(root, 'bin'), {recursive: true});
  for (const name of ['kitty', 'ghostty']) {
    const file = path.join(root, 'bin', name);
    await writeFile(file, '#!/bin/sh\nexit 0\n');
    await chmod(file, 0o755);
  }
  const config = path.join(root, 'config');
  for (const folder of ['kitty', 'ghostty', 'sway', 'waybar', 'gtk-3.0']) await mkdir(path.join(config, folder), {recursive: true});
  const original = 'font_size 15\n# Keep my existing preferences\n';
  await writeFile(path.join(config, 'kitty/kitty.conf'), original);
  await writeFile(path.join(config, 'ghostty/config'), 'font-size = 14\n');
  await writeFile(path.join(config, 'sway/config'), '# Existing Sway configuration\n');
  await writeFile(path.join(config, 'waybar/config'), '{}\n');
  await writeFile(path.join(config, 'gtk-3.0/settings.ini'), '[Settings]\ngtk-theme-name=Adwaita\ngtk-icon-theme-name=Papirus\n');
  await mkdir(output, {recursive: true});

  application = spawn(path.join(repo, 'bin/desktop-theming'), ['dashboard', '--no-browser'], {
    env: {...process.env, HOME: root, XDG_CONFIG_HOME: config, XDG_STATE_HOME: path.join(root, 'state'),
      XDG_CURRENT_DESKTOP: 'sway', XDG_SESSION_DESKTOP: 'sway', XDG_SESSION_TYPE: 'wayland', SWAYSOCK: '/fixture/sway.sock',
      PATH: `${path.join(root, 'bin')}:${process.env.PATH}`}, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let log = '';
  application.stdout.on('data', data => { log += data; });
  application.stderr.on('data', data => process.stderr.write(data));
  const origin = await until(() => log.match(/http:\/\/127\.0\.0\.1:\d+/)?.[0], 'application start');
  chromium = spawn(process.env.CHROMIUM || 'chromium', ['--headless=new', '--no-sandbox', '--disable-gpu',
    '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
    `--user-data-dir=${path.join(root, 'browser')}`, 'about:blank'], {stdio: ['ignore', 'ignore', 'ignore']});
  const port = await until(async () => {
    try { return (await readFile(path.join(root, 'browser/DevToolsActivePort'), 'utf8')).split('\n')[0]; }
    catch { return null; }
  }, 'browser start');
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  const pending = new Map();
  let sequence = 0;
  const errors = [];
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id) {
      const callbacks = pending.get(message.id);
      pending.delete(message.id);
      message.error ? callbacks.reject(new Error(message.error.message)) : callbacks.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const response = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails));
    return response.result.value;
  };
  const click = async selector => {
    const box = await evaluate(`(() => {const e=document.querySelector(${JSON.stringify(selector)}); if(!e || e.disabled) throw new Error('Missing or disabled control'); e.scrollIntoView({block:'center'}); const b=e.getBoundingClientRect(); return {x:b.x+b.width/2,y:b.y+b.height/2};})()`);
    await send('Input.dispatchMouseEvent', {...box, type: 'mousePressed', button: 'left', clickCount: 1});
    await send('Input.dispatchMouseEvent', {...box, type: 'mouseReleased', button: 'left', clickCount: 1});
  };
  const screenshot = async name => {
    const value = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
    await writeFile(path.join(output, name), Buffer.from(value.data, 'base64'));
  };
  await send('Runtime.enable');
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1050, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url: origin});
  await until(() => evaluate(`document.querySelector('#desktop')?.textContent === 'sway' && document.querySelectorAll('.swatch').length === 16`), 'inventory and palette');
  assert.equal(await evaluate(`document.querySelector('#notice').hidden`), true, 'no initial error');
  assert.equal(await evaluate(`document.querySelectorAll('.component-card.selected').length`), 0, 'no automatic enrollment');
  await screenshot('desktop-overview.png');
  await click('input[aria-label="Connect kitty to the theme"]');
  await click('#review');
  await until(() => evaluate(`document.querySelector('#review-dialog').open && !document.querySelector('#apply').disabled`), 'file review');
  assert.equal(await readFile(path.join(config, 'kitty/kitty.conf'), 'utf8'), original, 'review is read-only');
  await screenshot('review-changes.png');
  await click('#apply');
  await until(() => evaluate(`!document.querySelector('#review-dialog').open && document.querySelector('#managed-count').textContent === '1'`), 'apply');
  assert.match(await readFile(path.join(config, 'kitty/kitty.conf'), 'utf8'), /BEGIN desktop-theming/);
  assert.equal(await readFile(path.join(config, 'ghostty/config'), 'utf8'), 'font-size = 14\n', 'unselected terminal unchanged');
  await click('#transactions button');
  await until(() => evaluate(`document.querySelector('#undo-dialog').open`), 'undo approval');
  await click('#confirm-undo');
  await until(() => evaluate(`!document.querySelector('#undo-dialog').open && document.querySelector('#managed-count').textContent === '0'`), 'undo');
  assert.equal(await readFile(path.join(config, 'kitty/kitty.conf'), 'utf8'), original, 'undo restores original bytes');
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await evaluate('window.scrollTo(0,0)');
  await pause(200);
  const metrics = await evaluate('({scroll:document.documentElement.scrollWidth,viewport:window.innerWidth,visual:window.visualViewport.width})');
  assert.ok(metrics.scroll <= 390, `no mobile horizontal overflow: ${JSON.stringify(metrics)}`);
  await screenshot('mobile-overview.png');
  assert.deepEqual(errors, [], 'no JavaScript exceptions');
  console.log(`Browser acceptance passed: inventory → select → review → approve → undo; mobile layout.\nScreenshots: ${output}`);
} finally {
  socket?.close();
  const stop = async process => {
    if (!process || process.exitCode !== null) return;
    process.kill('SIGTERM');
    await Promise.race([new Promise(resolve => process.once('exit', resolve)), pause(2000)]);
    if (process.exitCode === null) process.kill('SIGKILL');
  };
  await stop(chromium);
  await stop(application);
  if (process.env.SCREENSHOT_DIR) await rm(root, {recursive: true, force: true});
}
