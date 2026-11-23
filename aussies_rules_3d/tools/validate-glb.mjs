/**
 * Khronos glTF validator wrapper for CI — one line per file, exit 1 on any error.
 *
 *   npm i --no-save gltf-validator@2.0.0-dev.3.10
 *   node tools/validate-glb.mjs file1.glb [file2.glb ...] >> $GITHUB_STEP_SUMMARY
 */
import { readFileSync } from 'node:fs';
import { validateBytes } from 'gltf-validator';

let bad = 0;
for (const file of process.argv.slice(2)) {
  const data = new Uint8Array(readFileSync(file));
  const res = await validateBytes(data, { uri: file });
  const i = res.issues;
  const line = `| \`${file}\` | ${i.numErrors} | ${i.numWarnings} | ${i.numInfos} |`;
  console.log(line);
  if (i.numErrors > 0) {
    bad += 1;
    for (const m of i.messages.filter((m) => m.severity <= 1).slice(0, 10)) {
      console.log(`::error file=${file},title=${m.code}::${m.pointer ?? ''} ${m.message ?? ''}`);
    }
  }
}
process.exit(bad ? 1 : 0);
