// HD Fighter 2 online server. The room/lockstep relay lives in the shared
// module (shared/netplay/server) so Egyptian Fighter and TurboTumble64 use
// the same protocol; this file only adds HD Fighter's settings and web client.
const path = require('path');
const { createServer: createNetplayServer } = require('c-games-netplay-server');
const { hdFighter } = require('c-games-netplay-server/games');

function createServer() {
  return createNetplayServer(hdFighter, {
    static: [
      { route: '/', dir: path.join(__dirname, 'public') },
      { route: '/assets', dir: path.join(__dirname, '..', 'assets_hd') },
    ],
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT || 3000);
  const srv = createServer();
  srv.listen(port, '0.0.0.0').then((bound) => {
    console.log(`HD Fighter 2 server on http://0.0.0.0:${bound}`);
  }).catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { createServer };
