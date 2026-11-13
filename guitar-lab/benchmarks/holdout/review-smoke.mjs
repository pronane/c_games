// Automated UI fixtures only: exported test JSON is NOT human-labelled evidence.
import { chromium } from 'playwright-core';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, unlink } from 'node:fs/promises';
const wav=Buffer.alloc(44+16000*2);
wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);
wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);
wav.writeUInt32LE(16000,24);wav.writeUInt32LE(32000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);
wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
for(let i=0;i<16000;i++)wav.writeInt16LE(Math.round(Math.sin(i*2*Math.PI*440/16000)*5000),44+i*2);
const browser=await chromium.launch({executablePath:process.env.BROWSER_EXECUTABLE_PATH,headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
try{
 const page=await browser.newPage();const errors=[],requests=[];
 page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>requests.push({url:r.url(),method:r.method()}));
 const url=process.env.REVIEW_URL??'http://127.0.0.1:8765';await page.goto(url);
 await page.locator('#export').click();await page.getByRole('status').filter({hasText:'required'}).waitFor();
 await page.locator('#audio-file').setInputFiles({name:'automated-fixture.wav',mimeType:'audio/wav',buffer:wav});
 const digest=createHash('sha256').update(wav).digest('hex');
 await page.waitForFunction(hash=>document.querySelector('#source').textContent.includes(hash)&&Number.isFinite(document.querySelector('#player').duration),digest);
 await page.locator('#reviewer').fill('AUTOMATED-UI-FIXTURE-NOT-HUMAN-EVIDENCE');
 await page.locator('#add').click();await page.locator('#certify').check();await page.locator('#export').click();
 assert.match(await page.locator('#status').innerText(),/Check unique/);
 const row=page.locator('#notes tr').first();const inputs=row.locator('input');
 await inputs.nth(0).fill('automated-note');await inputs.nth(1).fill('0.1');await inputs.nth(2).fill('0.4');await inputs.nth(3).fill('69');
 await inputs.nth(4).fill('0.3');await row.locator('select').selectOption('correct');
 await inputs.nth(5).fill('Automated UI schema fixture only. No human judgement.');
 assert.equal(await page.locator('#certify').isChecked(),false);
 await page.locator('#certify').check();
 const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#export').click()]);
 const path=await download.path();const labels=JSON.parse(await readFile(path,'utf8'));
 assert.equal(labels.source_sha256,digest);assert.equal(labels.notes.length,1);assert.equal(labels.sustain.length,1);
 assert.equal(labels.notes[0].midi,69);assert.equal(labels.sustain[0].judgement,'correct');
 await unlink(path);
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.equal(errors.length,0);assert.ok(requests.every(r=>r.method==='GET'&&(r.url.startsWith(url)||r.url.startsWith('blob:'))));
 console.log(JSON.stringify({status:'pass',checks:['no unreviewed export','audio checksum','required note fields','review confirmation reset','JSON export','no network upload','mobile layout'],fixture:'AUTOMATED, NOT HUMAN EVIDENCE',browser_errors:errors}));
}finally{await browser.close();}
