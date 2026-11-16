import {build} from 'esbuild';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const output = resolve(root, '../terminal_bundle');
await mkdir(output, {recursive: true});
const result = await build({
  absWorkingDir: root, entryPoints: ['src/index.tsx'], outfile: resolve(output, 'postal.mjs'),
  platform: 'node', format: 'esm', target: 'node22', bundle: true, minify: true, metafile: true,
  define: {'process.env.NODE_ENV': '"production"'},
  plugins: [{name: 'omit-development-tools', setup(builder) {
    builder.onResolve({filter: /^\.\/devtools\.js$/}, args => args.importer.includes('/ink/') ? {path: 'devtools', namespace: 'production'} : undefined);
    builder.onLoad({filter: /.*/, namespace: 'production'}, () => ({contents: 'export {};', loader: 'js'}));
  }}],
  banner: {js: "import {createRequire as __createRequire} from 'node:module'; const require = __createRequire(import.meta.url);"},
});
// Ship license notices with the bundled runtime; users need Node, not npm dependencies.
const notices = [];
const seen = new Set();
for (const input of Object.keys(result.metafile.inputs)) {
  const match = input.match(/node_modules\/((?:@[^/]+\/)?[^/]+)/);
  if (!match || seen.has(match[1])) continue;
  seen.add(match[1]);
  let directory = resolve(root, 'node_modules', match[1]);
  try {
    const pkg = JSON.parse(await readFile(resolve(directory, 'package.json'), 'utf8'));
    let license = '';
    for (const name of ['LICENSE', 'license', 'LICENSE.md', 'LICENSE.txt']) {
      try { license = await readFile(resolve(directory, name), 'utf8'); break; } catch {}
    }
    notices.push(`${pkg.name} ${pkg.version} (${pkg.license || 'See package license'})\n${license}`);
  } catch {}
}
await writeFile(resolve(output, 'THIRD_PARTY_NOTICES.txt'), notices.join('\n\n---\n\n'));
console.log(`Built ${resolve(output, 'postal.mjs')}`);
