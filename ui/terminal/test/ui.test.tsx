import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {setTimeout as delay} from 'node:timers/promises';
import {renderToString} from 'ink';
import {render, cleanup} from 'ink-testing-library';
import stringWidth from 'string-width';
import stripAnsi from 'strip-ansi';
import {PostalApp, TerminalView} from '../src/App.js';
import {initialState} from '../src/state.js';
import type {ServerMessage, Settings, Transport} from '../src/protocol.js';

afterEach(cleanup);
const settings: Settings = {model: 'provider/a-very-long-model-name', cwd: '/workspace/postal', approval: 'ask',
  reasoning: {enabled: true, visible: true, effort: 'minimal', max_tokens: null}};
class Backend implements Transport {
  requests: {method: string; params: Record<string, unknown>}[] = [];
  listeners = new Set<(message: ServerMessage) => void>();
  subscribe(listener: (message: ServerMessage) => void) {
    this.listeners.add(listener);
    listener({type: 'ready', settings, history: ['previous prompt'], messages: [], version: 'test', logo: initialState.logo,
      capabilities: {read: true, search: true}, commands: [{name: 'help', description: 'Help'}, {name: 'model', description: 'Change model'}]});
    return () => { this.listeners.delete(listener); };
  }
  emit(message: ServerMessage) { for (const listener of this.listeners) listener(message); }
  async request<T = Record<string, unknown>>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    this.requests.push({method, params});
    if (method === 'submit') this.emit({type: 'turn_start', text: String(params.text), files: [], web: false});
    if (method === 'cancel') this.emit({type: 'turn_end', status: 'Interrupted'});
    if (method === 'model') this.emit({type: 'settings', settings: {...settings, model: String(params.model)}});
    return (method === 'file' ? {path: '/workspace/postal/app.py'} : {}) as T;
  }
  async close() {}
}
async function until(predicate: () => boolean) {
  for (let attempt = 0; attempt < 100; attempt++) { if (predicate()) return; await delay(10); }
  assert.ok(predicate(), 'UI did not reach the expected state');
}

test('centered home and prompt controls fit narrow, short, and wide terminals', () => {
  for (const [columns, rows] of [[140, 40], [100, 30], [80, 24], [50, 18], [40, 12]]) {
    const frame = stripAnsi(renderToString(<TerminalView columns={columns!} rows={rows!}
      state={{...initialState, ready: true, status: 'Ready', settings}} draft={{text: '', cursor: 0}} focus="input"
      files={[]} web={false} sending={false} action={() => {}} removeFiles={() => {}} removeWeb={() => {}}
      lines={[]} scroll={null} toggle={() => {}} toast=""/>, {columns}));
    const lines = frame.split('\n');
    assert.ok(lines.length <= rows!, `${columns}x${rows}: ${lines.length} lines`);
    assert.ok(lines.every(line => stringWidth(line) <= columns!), `${columns}x${rows}: horizontal overflow`);
    assert.ok(frame.includes('Ask anything'));
    assert.ok(frame.includes('↑'));
    const borderRow = lines.findIndex(line => line.includes('╭'));
    const border = lines[borderRow]!;
    assert.ok(Math.abs((border.indexOf('╭') + border.indexOf('╮') + 1) / 2 - columns! / 2) <= 1);
    assert.ok(Math.abs(borderRow + 3 - rows! / 2) <= 3);
  }
});

test('keyboard submission streams responses, preserves multiline input, and can cancel', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 100, rows: 30}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  app.stdin.write('first');
  await delay(30);
  app.stdin.write('\x1b[200~\nsecond\x1b[201~');
  await delay(30);
  app.stdin.write('\r');
  await until(() => backend.requests.some(request => request.method === 'submit'));
  assert.equal(backend.requests.find(request => request.method === 'submit')!.params.text, 'first\nsecond');
  backend.emit({type: 'agent_event', event: {type: 'text_delta', data: {content: 'Live Python response'}, agent_id: 'main', parent_agent_id: null}});
  await until(() => app.lastFrame()?.includes('Live Python response') ?? false);
  app.stdin.write('\x1b');
  await until(() => backend.requests.some(request => request.method === 'cancel'));
  await until(() => app.lastFrame()?.includes('Interrupted') ?? false);
});

test('approval defaults to reject and approval shortcuts are explicit', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 80, rows: 24}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  const approval = {id: 'approval-1', tool: 'write', description: 'Write app.py', params: {path: 'app.py'}, paths: ['app.py'], dangerous: false};
  backend.emit({type: 'approval', approval});
  await until(() => app.lastFrame()?.includes('Permission required') ?? false);
  app.stdin.write('\r');
  await until(() => backend.requests.some(request => request.method === 'approve'));
  assert.deepEqual(backend.requests.find(request => request.method === 'approve')!.params, {approvalId: 'approval-1', approved: false});
  backend.emit({type: 'approval_closed', id: 'approval-1'});
  backend.emit({type: 'approval', approval: {...approval, id: 'approval-2'}});
  await delay(40);
  app.stdin.write('y');
  await until(() => backend.requests.filter(request => request.method === 'approve').length === 2);
  assert.deepEqual(backend.requests.at(-1)!.params, {approvalId: 'approval-2', approved: true});
});

test('model picker keeps the draft and command completion is keyboard accessible', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 100, rows: 30}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  app.stdin.write('keep my draft');
  await delay(30);
  app.stdin.write('\t'); await delay(20);
  app.stdin.write('\t'); await delay(20);
  app.stdin.write('\r');
  await until(() => app.lastFrame()?.includes('Choose a model') ?? false);
  app.stdin.write('\x15'); await delay(20);
  app.stdin.write('provider/new'); await delay(20);
  app.stdin.write('\r');
  await until(() => backend.requests.some(request => request.method === 'model'));
  assert.equal(backend.requests.find(request => request.method === 'model')!.params.model, 'provider/new');
  await until(() => app.lastFrame()?.includes('keep my draft') ?? false);
  app.stdin.write('\x10');
  await until(() => app.lastFrame()?.includes('Commands') ?? false);
  app.stdin.write('he'); await delay(20);
  app.stdin.write('\t');
  await until(() => app.lastFrame()?.includes('/help ') ?? false);
  app.stdin.write('\x1b');
});
