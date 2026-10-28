# Arena FC - Play With Friends server container.
# Build from the repository root:  docker build -f Server/Dockerfile -t arenafc-server .
# Run:                            docker run -p 7777:7777 arenafc-server
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src
COPY . .
RUN dotnet publish Server/ArenaFC.Server.csproj -c Release -o /app --nologo

FROM mcr.microsoft.com/dotnet/runtime:9.0
WORKDIR /app
COPY --from=build /app .
ENV DOTNET_EnableDiagnostics=0
EXPOSE 7777
VOLUME ["/app/replays"]
# Set ARENA_FC_PEER_HOST=1 to also hand the running simulation to the new host
# when the host disconnects (default: server stays authoritative).
ENV ARENA_FC_PEER_HOST=0
ENTRYPOINT ["sh", "-c", "if [ \"$ARENA_FC_PEER_HOST\" = \"1\" ]; then exec dotnet ArenaFC.Server.dll --port 7777 --bind 0.0.0.0 --verbose --peer-host; else exec dotnet ArenaFC.Server.dll --port 7777 --bind 0.0.0.0 --verbose; fi"]
