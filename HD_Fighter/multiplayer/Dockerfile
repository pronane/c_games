# Build from the repository root (the server code is in shared/netplay/server):
#   docker build -f HD_Fighter/multiplayer/Dockerfile -t hd-fighter .
FROM node:20-slim
WORKDIR /app
COPY shared/netplay/server ./shared/netplay/server
COPY HD_Fighter/multiplayer ./HD_Fighter/multiplayer
COPY HD_Fighter/assets_hd ./HD_Fighter/assets_hd
WORKDIR /app/HD_Fighter/multiplayer
RUN npm install --omit=dev
EXPOSE 3000
CMD ["node","server.js"]
