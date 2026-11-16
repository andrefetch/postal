import {readFileSync} from 'node:fs';
import {parseArgs} from 'node:util';
import {render} from 'ink';
import {PostalApp} from './App.js';
import {PythonBackend} from './backend.js';
import {DemoBackend} from './demo.js';
import {MouseContext, terminalInput} from './mouse.js';

const {values} = parseArgs({options: {demo: {type: 'boolean'}, bootstrap: {type: 'string'}, python: {type: 'string'}}});
if (!values.demo && !values.bootstrap) throw new Error('Start Postal with the Python CLI, or use --demo for a local UI preview.');
const backend = values.demo ? new DemoBackend() : new PythonBackend(values.python || 'python3', JSON.parse(readFileSync(values.bootstrap!, 'utf8')));
const input = terminalInput(process.stdin);
const mouse = !!process.stdin.isTTY && !!process.stdout.isTTY;
if (mouse) process.stdout.write('\x1b[?1000h\x1b[?1006h');
const reset = () => { if (mouse) process.stdout.write('\x1b[?1000l\x1b[?1006l'); };
const emergency = () => { reset(); if (backend instanceof PythonBackend) backend.terminate(); };
process.once('exit', emergency);
const app = render(<MouseContext.Provider value={input.events}><PostalApp backend={backend}/></MouseContext.Provider>, {
  stdin: input.stream, alternateScreen: true, exitOnCtrlC: false, incrementalRendering: true, maxFps: 30,
});
const stop = () => { void backend.close().finally(() => app.unmount()); };
process.once('SIGTERM', stop);
process.once('SIGHUP', stop);
try { await app.waitUntilExit(); }
finally {
  await backend.close(); input.dispose(); reset(); process.stdin.pause();
  process.off('SIGTERM', stop); process.off('SIGHUP', stop); process.off('exit', emergency);
}
