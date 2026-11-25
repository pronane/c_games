/**
 * CI screenshot capture for the Aussies Rules Motion A/B workflow.
 *
 * Not part of the shipped app: loads the production build (dist/index.html)
 * exactly like electron/main.cjs does, waits for the attract demo to boot,
 * then saves N frames + a console-error log for A/B comparison.
 *
 *   electron tools/ci_capture.cjs --out build/motion-ab/original [--frames 30] [--interval-ms 600] [--settle-ms 15000]
 *
 * Software WebGL: hardware acceleration is disabled on purpose (CI runners
 * have no GPU); Chrome needs --enable-unsafe-swiftshader for software WebGL.
 */
const { app, BrowserWindow } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { createCaptureServer } = require('./capture_server.cjs');

app.commandLine.appendSwitch('enable-unsafe-swiftshader');
app.commandLine.appendSwitch('use-angle', 'swiftshader');
app.commandLine.appendSwitch('disable-gpu-sandbox');
try { app.disableHardwareAcceleration(); } catch { /* headless */ }

const take = (flag, fallback) => {
  const i = process.argv.indexOf(flag);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};
const OUT = path.resolve(take('--out', 'build/motion-ab'));
const QUERY_RAW = take('--query', '');
const QUERY = {};
for (const pair of QUERY_RAW.split('&').filter(Boolean)) {
  const i = pair.indexOf('=');
  if (i > 0) QUERY[pair.slice(0, i)] = decodeURIComponent(pair.slice(i + 1));
}
const FRAMES = Number(take('--frames', '30'));
const INTERVAL_MS = Number(take('--interval-ms', '600'));
const SETTLE_MS = Number(take('--settle-ms', '15000'));

fs.mkdirSync(OUT, { recursive: true });
const consoleLog = [];
let finishing = false;

function main() {
  const win = new BrowserWindow({
    width: 1440,
    height: 810,
    show: false,
    backgroundColor: '#0b1420',
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true, backgroundThrottling: false },
  });
  win.webContents.on('console-message', (_e, _level, message) => {
    consoleLog.push(message);
  });
  win.webContents.on('render-process-gone', (_e, details) => {
    consoleLog.push('RENDER PROCESS GONE: ' + JSON.stringify(details));
    finish(1);
  });

  // Exercise the browser build over HTTP, as users do. file:// fetch support
  // varies across Electron/Chromium and can strand GLB/JSON loading at startup.
  const server = createCaptureServer(path.resolve(__dirname, '..', 'dist'));
  server.on('error', err => { consoleLog.push('CAPTURE_SERVER_FAILED: ' + err); finish(1); });
  server.listen(0, '127.0.0.1', () => {
    const query = new URLSearchParams(QUERY).toString();
    win.loadURL(`http://127.0.0.1:${server.address().port}/index.html?${query}`)
      .catch(err => { consoleLog.push('LOAD_FAILED: ' + err); finish(1); });
  });

  // Never call a successfully loaded HTML page a successfully booted game.
  const deadline = Date.now() + 120000;
  const waitForGame = async () => {
    if (Date.now() > deadline) { consoleLog.push('CAPTURE_NOT_READY: game did not render within 120s'); return finish(1); }
    try {
      const ready = await win.webContents.executeJavaScript('window.__captureReady === true');
      if (ready) {
        consoleLog.push('CAPTURE_READY: first game frame rendered');
        return setTimeout(() => capture(win, 0), SETTLE_MS);
      }
    } catch (err) { consoleLog.push('readiness probe: ' + err); }
    setTimeout(waitForGame, 250);
  };
  win.webContents.once('did-finish-load', waitForGame);
  win.webContents.on('did-fail-load', (_event, code, description) => {
    consoleLog.push(`LOAD_FAILED ${code}: ${description}`); finish(1);
  });
  // Also covers a renderer IPC readiness probe that never resolves.
  setTimeout(() => { consoleLog.push('CAPTURE_TIMEOUT'); finish(1); }, 220000);
}

async function capture(win, i) {
  if (i >= FRAMES) return finish(0);
  if (QUERY.drive === 'manual') {
    try {
      const state = await win.webContents.executeJavaScript('window.__advanceCapture ? window.__advanceCapture(30) : null');
      if (!state) throw new Error('Scripted match did not become ready');
      fs.writeFileSync(path.join(OUT, `state-${String(i).padStart(3, '0')}.json`), JSON.stringify(state, null, 2));
    } catch (err) { consoleLog.push('capture scenario failed: ' + err); return finish(1); }
  }
  win.webContents.capturePage().then((img) => {
    const file = path.join(OUT, `frame-${String(i).padStart(3, '0')}.png`);
    try {
      fs.writeFileSync(file, img.toPNG());
      // A small set of game-only JPEGs can also travel through check annotations.
      if (QUERY.drive === 'manual' && i % 6 === 0) {
        let preview = img.resize({ width: 640 }).toJPEG(40);
        if (preview.length > 40000) preview = img.resize({ width: 480 }).toJPEG(30);
        fs.writeFileSync(path.join(OUT, `preview-${String(i).padStart(3, '0')}.jpg`), preview);
      }
    } catch (err) {
      consoleLog.push('capturePage failed: ' + err);
      return finish(1);
    }
    setTimeout(() => capture(win, i + 1), INTERVAL_MS);
  }).catch(err => { consoleLog.push('capturePage failed: ' + err); finish(1); });
}

function finish(code) {
  if (finishing) return;
  finishing = true;
  try {
    fs.writeFileSync(path.join(OUT, 'console.log'), consoleLog.join('\n'));
    const frames = fs.readdirSync(OUT).filter((f) => f.endsWith('.png'));
    let bytes = 0;
    for (const f of frames) bytes += fs.statSync(path.join(OUT, f)).size;
    fs.writeFileSync(
      path.join(OUT, 'summary.json'),
      JSON.stringify({ frames: frames.length, pngBytes: bytes, consoleLines: consoleLog.length }, null, 2)
    );
    console.log(`captured ${frames.length} frame(s), ${bytes} bytes, ${consoleLog.length} console lines`);
  } catch (err) {
    console.error('finish() error', err);
    code = 1;
  }
  process.exit(code);
}

app.whenReady().then(main);
