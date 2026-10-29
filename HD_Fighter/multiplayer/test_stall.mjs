import { evalStall, stallLabel, connectFailure, SLOW_MS, LOST_MS } from './public/stall.mjs';
import { packInput, unpackInput, encodeTail, absorbContig, gapBefore } from './public/wire.mjs';
import { chooseDelay, MAX_DELAY_FRAMES, FRAME_MS } from './public/pace.mjs';

function check(cond, msg) { if (!cond) throw new Error(msg); }

// Slow but alive: a packet at least every 200 ms for 30 s never stalls,
// even if the sim is behind the whole time.
{
  let last = 0;
  let worst = 'ok';
  for (let t = 0; t <= 30000; t += 50) {
    if (t - last >= 200) last = t;
    const level = evalStall(last, t);
    if (level === 'lost' || (level === 'slow' && worst !== 'lost')) worst = level;
    check(level === 'ok', `false stall at t=${t} level=${level}`);
  }
  check(worst === 'ok', worst);
}

// Blackholed peer: silence from t=0.
{
  check(evalStall(0, 999) === 'ok', 'early');
  check(evalStall(0, SLOW_MS) === 'slow', 'slow edge');
  check(stallLabel(evalStall(0, 5000)) === 'Connection slow', 'slow label');
  check(evalStall(0, LOST_MS - 1) === 'slow', 'still slow');
  check(evalStall(0, LOST_MS) === 'lost', 'lost edge');
  check(stallLabel('lost') === 'Connection lost', 'lost label');
}

// Packets resume → the indicator clears. A later silence can trip it again.
{
  let last = 0;
  check(evalStall(last, 1500) === 'slow', 'before resume');
  last = 1600;
  check(evalStall(last, 1600) === 'ok', 'resumed');
  check(evalStall(last, 1600 + SLOW_MS) === 'slow', 'silent again');
  last = 1600 + SLOW_MS + 10;
  check(evalStall(last, last) === 'ok', 'recovered from slow');
  check(evalStall(0, LOST_MS + 100) === 'lost', 'lost while blackholed');
  check(evalStall(LOST_MS + 100, LOST_MS + 100) === 'ok', 'recovered from lost');
}

// Frame lag alone must not count. Packets every 30 ms for 21 s stay ok.
{
  let last = 0;
  for (let t = 0; t <= 21300; t += 30) {
    last = t;
    const blocked = true;
    check(blocked && evalStall(last, t) === 'ok', 'false lost at ' + t);
  }
}

{
  const inp = unpackInput(packInput({ left: true, hp: true, super: true }));
  check(inp.left && inp.hp && inp.super && !inp.right && !inp.lp, 'pack roundtrip ' + JSON.stringify(inp));
}

{
  const log = [];
  for (let f = 0; f < 60; f++) log.push({ frame: f, inp: { left: f % 2 === 0 } });
  let bytes = 0;
  let packets = 0;
  for (let ack = -1; ack < 59; ack++) {
    const enc = encodeTail(log, ack);
    check(enc && ((enc.bits && enc.bits.length <= 32) || (enc.batch && enc.batch.length <= 32)), 'tail too long');
    bytes += JSON.stringify({ t: 'input', ack, ...enc }).length;
    packets += 1;
  }
  check(bytes < 25000, `steady upload ${bytes} bytes for ${packets} packets`);
  const have = new Set([0, 1, 2]);
  check(absorbContig(-1, have) === 2, 'contig');
  const gap = gapBefore(2, [6, 7]);
  check(gap && gap.from === 3 && gap.to === 5, 'gap ' + JSON.stringify(gap));
  check(gapBefore(6, [7]) === null, 'no gap on the next frame');
}

{
  const both = { rtt: 240, jitter: 80, samples: 8 };
  const delay = chooseDelay(both, both);
  const cover = delay * FRAME_MS;
  check(delay >= 18 && delay < MAX_DELAY_FRAMES, '120ms profile delay ' + delay);
  check(cover >= 240, 'delay does not cover one-way ' + cover);
  const thin = chooseDelay({ rtt: 240, jitter: 0, samples: 1 }, { rtt: 240, jitter: 0, samples: 1 });
  check(thin <= MAX_DELAY_FRAMES && thin * FRAME_MS >= 240, 'thin sample delay ' + thin);
  check(chooseDelay(null, null) === 3, 'default delay');
}

{
  const refused = connectFailure({ networkError: true });
  check(refused.text === "Can't reach the server." && refused.clearPill && !refused.waking, 'refused');
  const waking = connectFailure({ networkError: false, httpStatus: 503 });
  check(waking.text === 'Waking the server...' && waking.waking && !waking.clearPill, '503');
}

console.log(JSON.stringify({ ok: true, slowMs: SLOW_MS, lostMs: LOST_MS }));
