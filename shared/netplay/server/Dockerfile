# One server for every online c_games title. Build from the repository root:
#   docker build -f shared/netplay/server/Dockerfile -t c-games-netplay .
FROM node:20-slim
WORKDIR /app
COPY shared/netplay/server ./shared/netplay/server
COPY HD_Fighter/multiplayer/public ./HD_Fighter/multiplayer/public
COPY HD_Fighter/assets_hd ./HD_Fighter/assets_hd
WORKDIR /app/shared/netplay/server
RUN npm install --omit=dev
EXPOSE 3000
CMD ["node","hub.js"]
