import {cp, mkdir, readFile, rm, writeFile, access} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {join, resolve} from 'node:path';

const project = fileURLToPath(new URL('.', import.meta.url));
const repository = resolve(project, '../..');
const output = join(project, 'dist');
const source = join(project, 'src');
const manifestPath = join(project, '.openai/hosting.json');
let manifest = {};
try { manifest = JSON.parse(await readFile(manifestPath, 'utf8')); }
catch (error) { if (error.code !== 'ENOENT') throw error; }

// In the full simulation checkout, web/ is authoritative. Commit this source
// snapshot with the Site so its independent repository can reproduce the build.
let hasUpstream = false;
try { await access(join(repository, 'web/lab/index.html')); hasUpstream = true; }
catch (error) { if (error.code !== 'ENOENT') throw error; }
if (hasUpstream) {
  await mkdir(source, {recursive: true});
  for (const directory of ['lab', 'vendor']) {
    await rm(join(source, directory), {recursive: true, force: true});
    await cp(join(repository, 'web', directory), join(source, directory), {recursive: true});
  }
}
await access(join(source, 'lab/index.html'));
await access(join(source, 'vendor/three.module.js'));
// Only the generated output in this isolated Site is replaced.
await rm(output, {recursive: true, force: true});
await mkdir(join(output, 'client'), {recursive: true});
await cp(join(source, 'lab'), join(output, 'client/lab'), {recursive: true});
await cp(join(source, 'vendor'), join(output, 'client/vendor'), {recursive: true});
await writeFile(join(output, 'client/index.html'), '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="0;url=/lab/"><title>Pelagic Reef Lab</title></head><body><a href="/lab/">Open Pelagic Reef Lab</a></body></html>\n');
const worker = await readFile(join(project, 'worker.mjs'), 'utf8');
const module = await import(`data:text/javascript;base64,${Buffer.from(worker).toString('base64')}`);
if (typeof module.default?.fetch !== 'function') throw new Error('Worker must export default.fetch');
if (!manifest.static) {
  await mkdir(join(output, 'server'), {recursive: true});
  await writeFile(join(output, 'server/index.js'), worker);
}
if (Object.keys(manifest).length) {
  await mkdir(join(output, '.openai'), {recursive: true});
  await cp(manifestPath, join(output, '.openai/hosting.json'));
}
console.log(`Built ${output}: ${manifest.static ? 'static client (scripted control)' : 'client and Worker (requires ASSETS binding)'}.`);
