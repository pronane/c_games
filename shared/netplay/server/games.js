// Per-game relay settings. Pick ids must match what each client sends in {t:'pick'}.
const path = require('path');

const root = path.join(__dirname, '..', '..', '..');

const hdFighter = {
  name: 'hd-fighter',
  picks: ['kairo', 'lyra', 'naomi', 'brutus', 'void', 'zap'],
  pickLabel: 'fighter',
  inputKeys: [
    'left', 'right', 'up', 'down', 'jump',
    'lp', 'hp', 'lk', 'hk', 'block', 'throw',
    'special1', 'special2', 'super',
  ],
  histMax: 6400, // a little over a 99 s round at 60 Hz
};

// Picks are the index into the character grid ("0".."6"). Bits: see egyptian_fighter/src/online.c.
const egyptianFighter = {
  name: 'egyptian-fighter',
  picks: ['0', '1', '2', '3', '4', '5', '6'],
  pickLabel: 'fighter',
  inputKeys: ['left', 'right', 'up', 'down', 'punch', 'kick', 'special1', 'special2', 'block', 'throw', 'taunt'],
  histMax: 6400,
};

// Picks are "<character>:<track>" so both players agree on the track; slot 0's track is used.
// Bits: see TurboTumble64/src/online.c (5-bit steer + buttons).
const turboTumble = {
  name: 'turbotumble64',
  picks: null,
  pickLabel: 'racer',
  inputKeys: [],
  histMax: 60 * 60 * 6, // six minutes of race
};

// Arena FC is a different kind of game: its authoritative server is the .NET program in arena-fc/Server,
// not a lockstep relay. The hub serves its browser build and proxies /arena/ws to that server.
// Opt-in: set ARENA_BACKEND (e.g. ws://127.0.0.1:7777) so existing deployments keep their exact routes.
const arenaFc = process.env.ARENA_BACKEND ? {
  path: '/arena',
  name: 'arena-fc',
  proxy: { target: process.env.ARENA_BACKEND, wsPath: '/ws' },
  static: [{ route: '/', dir: process.env.ARENA_WEB_DIR || path.join(root, 'arena-fc', 'build', 'web') }],
} : null;

const hubGames = [
  {
    path: '/',
    game: hdFighter,
    static: [
      { route: '/', dir: path.join(root, 'HD_Fighter', 'multiplayer', 'public') },
      { route: '/assets', dir: path.join(root, 'HD_Fighter', 'assets_hd') },
    ],
  },
  { path: '/egyptian', game: egyptianFighter },
  { path: '/turbo', game: turboTumble },
].concat(arenaFc ? [arenaFc] : []);

module.exports = { hdFighter, egyptianFighter, turboTumble, hubGames };
