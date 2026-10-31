# Arena FC online: .NET authoritative server + the shared Node hub, one container.
# Build from the REPOSITORY ROOT (the hub lives in shared/netplay/server):
#   docker build -f arena-fc/option-b/Dockerfile -t c-games .
# Needs arena-fc/build/web (the Godot Web export) to exist first - see option-b/README.md.
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src
COPY arena-fc/Server arena-fc/Server
COPY arena-fc/Scripts/Core arena-fc/Scripts/Core
RUN dotnet publish arena-fc/Server/ArenaFC.Server.csproj -c Release -o /app/publish --nologo

FROM mcr.microsoft.com/dotnet/runtime:9.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ENV DOTNET_EnableDiagnostics=0 DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 PORT=10000 TRUST_PROXY=1
WORKDIR /app
COPY --from=build /app/publish ./server/
COPY shared/netplay/server ./shared/netplay/server
RUN cd shared/netplay/server && npm install --omit=dev --no-audit --no-fund
COPY HD_Fighter/multiplayer/public ./HD_Fighter/multiplayer/public
COPY HD_Fighter/assets_hd ./HD_Fighter/assets_hd
COPY arena-fc/build/web ./arena-fc/build/web
COPY arena-fc/option-b/start.sh /app/start.sh
RUN chmod +x /app/start.sh
EXPOSE 10000
CMD ["/app/start.sh"]
