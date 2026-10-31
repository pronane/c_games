// One process for every online c_games title (one Render free instance).
//   ws(s)://host/          HD Fighter (and its web client at /)
//   ws(s)://host/egyptian  Egyptian Fighter
//   ws(s)://host/turbo     TurboTumble64
//   ws(s)://host/arena/ws  Arena FC (only when ARENA_BACKEND is set; page at /arena/)
const { createHub } = require('./index');
const { hubGames } = require('./games');

const port = Number(process.env.PORT || 3000);
createHub(hubGames).listen(port, '0.0.0.0').then((bound) => {
  console.log(`c_games netplay hub on http://0.0.0.0:${bound} (${hubGames.map((g) => g.path).join(' ')})`);
}).catch((err) => {
  console.error(err);
  process.exit(1);
});
