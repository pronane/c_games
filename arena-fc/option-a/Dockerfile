# Arena FC online on the shared Node hub alone: no .NET. Build from the repository root after exporting the
# web build (godot --headless --export-release "Web" arena-fc/build/web/index.html):
#   docker build -f arena-fc/option-a/Dockerfile -t c-games-arena .
#   docker run --rm -p 10000:10000 c-games-arena        # http://localhost:10000/arena/
FROM node:20-slim
WORKDIR /app
COPY shared/netplay/server ./shared/netplay/server
COPY HD_Fighter/multiplayer/public ./HD_Fighter/multiplayer/public
COPY HD_Fighter/assets_hd ./HD_Fighter/assets_hd
COPY arena-fc/build/web ./arena-fc/build/web
WORKDIR /app/shared/netplay/server
RUN npm install --omit=dev
ENV ARENA_NATIVE=1 TRUST_PROXY=1 PORT=10000
EXPOSE 10000
CMD ["node","hub.js"]
