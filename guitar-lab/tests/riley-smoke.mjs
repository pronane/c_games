// Actual default Riley inference on a real bundled guitar recording; not the beep fixture.
import { chromium } from 'playwright-core';
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const root = new URL('../benchmarks/regression/data/guitarset/', import.meta.url);
const audio = await readFile(new URL('05_Rock1-90-C#_solo_mic.wav', root));
const truth = JSON.parse(await readFile(new URL('05_Rock1-90-C#_solo.notes.json', root), 'utf8'));
const browser = await chromium.launch({executablePath:process.env.BROWSER_EXECUTABLE_PATH, headless:true,
  args:['--no-sandbox','--disable-dev-shm-usage']});
try {
  const page = await browser.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(process.env.STUDIO_URL ?? 'http://127.0.0.1:5173');
  await page.waitForFunction(()=>document.querySelectorAll('#transcriber').length &&
    [...document.querySelectorAll('#transcriber')].every(x=>x.value==='riley'));
  const result = await page.evaluate(async ({b64,notes})=>{
    const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
    const form=new FormData();form.append('take',new Blob([bytes],{type:'audio/wav'}),'guitar.wav');
    form.append('targets',JSON.stringify([{source:'file',notes}]));
    const r=await fetch('/api/compare',{method:'POST',headers:{'X-Fretwork-Client':'studio'},body:form});
    return {status:r.status,body:await r.json()};
  },{b64:audio.toString('base64'),notes:truth.notes});
  assert.equal(result.status,200);assert.match(result.body.transcription,/Riley/);
  assert.ok(result.body.take_notes.length>0);assert.equal(errors.length,0);
  console.log(JSON.stringify({status:result.status,transcription:result.body.transcription,
    note_count:result.body.take_notes.length,duration_policy:result.body.reports[0].duration_policy,
    browser_errors:errors}));
} finally { await browser.close(); }
