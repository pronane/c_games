import { test } from 'node:test';
import assert from 'node:assert/strict';
import { compareTake, compareSongTake } from './songApi';

test('comparison clients carry the selected detector in multipart requests', async () => {
  const original = globalThis.fetch;
  const requests: {url: string; body: FormData}[] = [];
  globalThis.fetch = async (url, init) => {
    requests.push({url: String(url), body: init!.body as FormData});
    return new Response(JSON.stringify({reports: [], combined: null}), {status: 200});
  };
  try {
    await compareTake({take: new Blob(['audio']), targets: [], transcriber: 'basic_pitch'});
    await compareSongTake('song-id', new Blob(['audio']), {
      parts:['guitar'], role:'any', tuning:'standard', capo:0, start:0, end:8, speed:1, transcriber:'riley',
    });
    assert.equal(requests[0].url, '/api/compare');
    assert.equal(requests[0].body.get('transcriber'), 'basic_pitch');
    assert.equal(requests[1].url, '/api/songs/song-id/compare');
    assert.equal(requests[1].body.get('transcriber'), 'riley');
    await compareTake({takeNotes: [], targets: []});
    assert.equal(requests[2].body.has('transcriber'), false);
  } finally { globalThis.fetch = original; }
});
