/**
 * Aussie Rules 3D — desktop shell (Electron).
 *
 * Loads the production build (dist/) over file:// — no server required.
 * Build first (`npm run build`), then `npm run desktop`.
 *
 * Intentionally minimal:
 *   - contextIsolation + sandbox on, nodeIntegration off (the game is a
 *     plain web app with no Node dependencies),
 *   - window.open / target=_blank links are pushed to the system browser,
 *   - friendly error page when dist/ is missing instead of a blank window.
 */
const { app, BrowserWindow, shell, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

const DIST_INDEX = path.join(__dirname, '..', 'dist', 'index.html');

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 810,
    minWidth: 960,
    minHeight: 540,
    backgroundColor: '#0b1420',
    title: 'Aussie Rules 3D',
    icon: path.join(__dirname, '..', 'public', 'icon-512.png'),
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // External links leave the app; in-app navigation stays internal.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });

  if (!fs.existsSync(DIST_INDEX)) {
    dialog.showErrorBox(
      'Aussie Rules 3D — build missing',
      'The production build was not found at dist/index.html.\n\n' +
        'Run `npm install && npm run build` first, then `npm run desktop`.',
    );
    win.loadURL(
      'data:text/html,<body style="background:#0b1420;color:#e8eef7;font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0"><div><h1>Build missing</h1><p>Run <code>npm install &amp;&amp; npm run build</code>, then <code>npm run desktop</code>.</p></div></body>',
    );
    return;
  }
  win.loadFile(DIST_INDEX);
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
