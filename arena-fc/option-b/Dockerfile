# Multi-stage Dockerfile: build .NET server, install Node for the edge proxy,
# run both in one container. Node edge is the public face; .NET is internal.
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Restore dependencies first (better Docker layer caching)
COPY ["Server/ArenaFC.Server.csproj", "Server/"]
RUN dotnet restore "Server/ArenaFC.Server.csproj"

# Build and publish the .NET server
COPY . .
WORKDIR /src/Server
RUN dotnet publish "ArenaFC.Server.csproj" -c Release -o /app/publish

# Runtime image: .NET ASP.NET runtime + Node.js for the edge proxy
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app

# Install Node.js (required by the edge proxy)
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy published .NET app
COPY --from=build /app/publish ./server/

# Create edge directory and copy Node proxy
WORKDIR /app/edge
COPY edge/package.json ./
RUN npm install --production
COPY edge/ ./

# Expose the Render-injected PORT (Node edge listens here)
EXPOSE 10000

# Start .NET server on localhost:7777 (internal), then Node edge on $PORT (public)
# Use 'sh -c' so both processes run; .NET goes to background, Node stays foreground.
CMD ["sh", "-c", "dotnet /app/server/ArenaFC.Server.dll --urls http://127.0.0.1:7777 & node server.js"]
