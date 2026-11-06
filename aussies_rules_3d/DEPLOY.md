# Deploy — run it anywhere

Aussie Rules 3D is a **static web app**: `npm run build` produces a `dist/`
folder (HTML + JS + CSS + GLB models) that runs on any static host, any OS,
any device. There is no backend to manage.

## 1. Build

```bash
./install.sh     # once
npx vite build   # → dist/
```

## 2. Any static host

Copy `dist/` to any of:

| Host | How |
|---|---|
| **GitHub Pages** | push `dist/` to a `gh-pages` branch, or use an Actions workflow with `peaceiris/actions-gh-pages`; `vite.config.ts` already sets `base: './'` so relative paths work in a subdirectory |
| **Netlify** | drag-and-drop `dist/`, or `netlify deploy --prod --dir=dist` |
| **Vercel** | `vercel deploy --prod` (build command `npx vite build`, output `dist`) |
| **Cloudflare Pages / Firebase Hosting / S3+CloudFront** | upload `dist/` |
| **Any web server (nginx, Apache, Caddy)** | serve `dist/` as the document root |

The service worker (`sw.js`) caches the models for **offline play** and the
web app manifest makes the game **installable on phones, tablets and desktops**
from the browser.

## 3. Your own machine / LAN

```bash
./start.sh            # http://localhost:8080
./start.sh --port 80  # needs elevated permissions for port 80
```

The server binds `0.0.0.0`, so phones, tablets and consoles on the same
network can play at `http://<host-ip>:8080`.

## 4. Docker (optional)

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY . .
RUN npm install && npx vite build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

```bash
docker build -t aussie-rules-3d .
docker run -p 8080:80 aussie-rules-3d
```

## 5. CI verification

`npm run verify` is CI-friendly (exit code 0/1): it runs TypeScript, the full
test suite, the production build and the glTF asset checks. A GitHub Actions
job is as simple as:

```yaml
- run: npm install
- run: npm run verify
```

## Performance notes

The whole game is ~3.5 MB uncompressed (593 KB three.js + 110 KB game code +
3.3 MB GLB models, well under 1 MB gzipped JS). It runs at 60 fps on modern
phones; the renderer caps pixel ratio at 1.75 and the crowd is a single
instanced draw call.
