import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {setTimeout as delay} from 'node:timers/promises';
import {renderToString} from 'ink';
import {render, cleanup} from 'ink-testing-library';
import stringWidth from 'string-width';
import stripAnsi from 'strip-ansi';
import {layout, PostalApp, TerminalView} from '../src/App.js';
import {initialState} from '../src/state.js';
import type {ServerMessage, Settings, Transport} from '../src/protocol.js';

afterEach(cleanup);
// ApprovalPolicy values sent by the picker, labels returned by Python, and UI text.
const approvalModes = [
  ['on_request', 'ask', 'Ask'],
  ['on_fail', 'on fail', 'On fail'],
  ['auto', 'auto', 'Auto'],
  ['auto_edit', 'auto-edit', 'Auto-edit'],
  ['never', 'read-only', 'Read-only'],
  ['yolo', 'yolo', 'Yolo'],
] as const;
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
    if (method === 'approval') this.emit({type: 'settings', settings: {...settings, approval: approvalModes.find(([mode]) => mode === params.mode)![1]}});
    return (method === 'file' ? {path: '/workspace/postal/app.py'} : {}) as T;
  }
  async close() {}
}
async function until(predicate: () => boolean) {
  for (let attempt = 0; attempt < 100; attempt++) { if (predicate()) return; await delay(10); }
  assert.ok(predicate(), 'UI did not reach the expected state');
}

test('centered home and prompt controls fit narrow, short, and wide terminals', () => {
  for (const [columns, rows] of [[140, 40], [100, 30], [80, 24], [50, 18], [40, 12], [32, 10]]) {
    for (const [files, web] of [[[], false], [['app.py'], false], [[], true], [['app.py'], true]] as const) {
      const dimensions = layout(columns!, rows!, true, {text: '', cursor: 0}, files.length > 0 || web);
      const frame = stripAnsi(renderToString(<TerminalView columns={columns!} rows={rows!}
        state={{...initialState, ready: true, status: 'Ready', settings}} draft={{text: '', cursor: 0}} focus="input"
        files={[...files]} web={web} sending={false} action={() => {}} removeFiles={() => {}} removeWeb={() => {}}
        lines={[]} scroll={null} toggle={() => {}} toast=""/>, {columns}));
      const lines = frame.split('\n');
      assert.ok(lines.length <= rows!, `${columns}x${rows}: ${lines.length} lines`);
      assert.ok(lines.every(line => stringWidth(line) <= columns!), `${columns}x${rows}: horizontal overflow`);
      assert.ok(frame.includes('Ask anything'));
      assert.ok(!frame.includes('↑'));
      assert.ok(frame.includes('Ready · ask'), `${columns}x${rows}: status hidden with files=${files.length}, web=${web}`);
      if (files.length) assert.ok(frame.includes('app.py ×'));
      if (web) assert.ok(frame.includes('Web ×'));
      for (const row of initialState.logo.slice(Math.max(0, initialState.logo.length - dimensions.welcome))) assert.ok(frame.includes(row.trim()), 'cloud is clipped');
      assert.ok(!frame.includes('p o s t a l'));
      const borderRow = lines.findIndex(line => line.includes('╭'));
      const border = lines[borderRow]!;
      assert.ok(Math.abs((border.indexOf('╭') + border.indexOf('╮') + 1) / 2 - columns! / 2) <= 1);
      assert.ok(Math.abs(borderRow + 3 - rows! / 2) <= 3);
    }
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
  assert.ok(app.lastFrame()?.includes('Postal'));
  assert.ok(!app.lastFrame()?.includes('Assistant'));
  app.stdin.write('\x1b');
  await until(() => backend.requests.some(request => request.method === 'cancel'));
  await until(() => app.lastFrame()?.includes('Interrupted') ?? false);
});

test('snow stays outside the cloud and prompt while the home background animates', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 100, rows: 30}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  await delay(1500);
  const lines = stripAnsi(app.lastFrame() ?? '').split('\n');
  assert.ok(/[·∙✦❄]/.test(lines.slice(2).join('\n')));
  const top = lines.findIndex(line => line.includes('╭')), bottom = lines.findIndex(line => line.includes('╰'));
  const left = lines[top]!.indexOf('╭'), right = lines[top]!.indexOf('╮');
  assert.ok(!/[∙✦❄]/.test(lines.slice(top, bottom + 1).map(line => line.slice(left, right + 1)).join('\n')));
  const cloud = lines.findIndex(line => line.includes('████████'));
  assert.ok(!/[·∙✦❄]/.test(lines.slice(cloud, cloud + 4).map(line => line.slice(38, 62)).join('\n')));
  assert.ok(lines.every(line => stringWidth(line) <= 100));
  assert.equal(lines.length, 30);
});

test('loading animates during thinking and tools, pauses for approval, and stops after interruption', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 80, rows: 24}}/>);
  const spinner = () => {
    const frame = stripAnsi(app.lastFrame() ?? '');
    if (frame.includes('Awaiting approval')) return undefined;
    return frame.match(/[\u2801-\u28ff]{2}/)?.[0] ?? frame.match(/Thinking… (\d+\.\d+s)/)?.[1];
  };
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  assert.equal(spinner(), undefined);
  backend.emit({type: 'turn_start', text: 'Inspect this project', files: [], web: false});
  await until(() => spinner() !== undefined);
  const first = spinner();
  await until(() => spinner() !== first);
  assert.ok(app.lastFrame()?.includes('Thinking'));
  const thinkingFrame = stripAnsi(app.lastFrame() ?? '').split('\n');
  assert.ok(thinkingFrame.findIndex(line => line.includes('Thinking')) < thinkingFrame.findIndex(line => line.includes('╭')),
    'thinking animation belongs above the prompt, inside the conversation');
  assert.ok(!thinkingFrame.slice(thinkingFrame.findIndex(line => line.includes('╰')) + 1).some(line => /[\u2801-\u28ff]{2}/.test(line)),
    'footer should not contain the loading animation');
  backend.emit({type: 'agent_event', event: {type: 'tool_call_start', agent_id: 'main', parent_agent_id: null,
    data: {call_id: 'read-1', name: 'read', arguments: {path: 'app.py'}}}});
  await until(() => app.lastFrame()?.includes('read app.py') ?? false);
  backend.emit({type: 'approval', approval: {id: 'approval-1', tool: 'read', description: 'Read app.py', params: {}, paths: [], dangerous: false}});
  await until(() => app.lastFrame()?.includes('Awaiting approval') ?? false);
  assert.equal(spinner(), undefined);
  backend.emit({type: 'approval_closed', id: 'approval-1'});
  await until(() => spinner() !== undefined);
  backend.emit({type: 'turn_end', status: 'Interrupted'});
  await until(() => app.lastFrame()?.includes('Interrupted') ?? false);
  assert.equal(spinner(), undefined);
  await delay(200);
  assert.equal(spinner(), undefined);
  assert.ok(app.lastFrame()?.includes('Interrupted'));
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

test('thinking uses a collapsible ThoughtLine with the compact lattice', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 80, rows: 30}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  backend.emit({type: 'turn_start', text: 'Inspect the project', files: [], web: false});
  backend.emit({type: 'agent_event', event: {type: 'reasoning_delta', agent_id: 'main', parent_agent_id: null,
    data: {content: 'First reasoning step\nSecond step\nThird step\nFourth step\nReading the supplied question\nConsidering the relevant code'}}});
  await until(() => app.lastFrame()?.includes('Considering the relevant code') ?? false);
  assert.match(app.lastFrame() ?? '', /[\u2801-\u28ff]{2} Thinking…/);
  assert.ok(!app.lastFrame()?.includes('First reasoning step'));
  app.stdin.write('\x0f');
  await until(() => app.lastFrame()?.includes('First reasoning step') ?? false);
  app.stdin.write('\x0f');
  await until(() => !app.lastFrame()?.includes('First reasoning step'));
  assert.ok(app.lastFrame()?.includes('Considering the relevant code'));
  backend.emit({type: 'agent_event', event: {type: 'reasoning_complete', agent_id: 'main', parent_agent_id: null, data: {}}});
  await until(() => app.lastFrame()?.includes('Thought for') ?? false);
  await until(() => !app.lastFrame()?.includes('Considering the relevant code'));
  app.stdin.write('\x0f');
  await until(() => app.lastFrame()?.includes('Considering the relevant code') ?? false);
  backend.emit({type: 'agent_event', event: {type: 'tool_call_start', agent_id: 'main', parent_agent_id: null,
    data: {call_id: 'read-1', name: 'read', arguments: {path: 'src/app.py'}}}});
  await until(() => app.lastFrame()?.includes('Running') ?? false);
  assert.ok(/[\u2801-\u28ff]{2}/.test(app.lastFrame() ?? ''));
  backend.emit({type: 'turn_end', status: 'Ready'});
});

test('scrolling keeps visible content anchored while earlier thoughts and tools compact', async t => {
  let now = 1000;
  t.mock.method(Date, 'now', () => now);
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 80, rows: 24}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  backend.emit({type: 'turn_start', text: 'Inspect the project', files: [], web: false});
  backend.emit({type: 'agent_event', event: {type: 'reasoning_delta', agent_id: 'main', parent_agent_id: null,
    data: {content: 'Step one\nStep two\nStep three\nStep four'}}});
  backend.emit({type: 'agent_event', event: {type: 'reasoning_complete', agent_id: 'main', parent_agent_id: null, data: {}}});
  for (const call_id of ['1', '2']) {
    backend.emit({type: 'agent_event', event: {type: 'tool_call_start', agent_id: 'main', parent_agent_id: null,
      data: {call_id, name: 'read', arguments: {path: `file${call_id}`}}}});
    backend.emit({type: 'agent_event', event: {type: 'tool_call_complete', agent_id: 'main', parent_agent_id: null,
      data: {call_id, success: true, output: 'A complete result'}}});
  }
  backend.emit({type: 'notice', text: Array.from({length: 100}, (_, i) => `Visible content ${i}`).join('\n')});
  backend.emit({type: 'turn_end', status: 'Ready'});
  await until(() => app.lastFrame()?.includes('Visible content 99') ?? false);
  app.stdin.write('\x1b[5~');
  await until(() => app.lastFrame()?.includes('pgdn latest') ?? false);
  const viewport = () => stripAnsi(app.lastFrame() ?? '').split('\n').slice(2, 14).map(line => line.trim());
  const anchored = viewport();
  assert.match(anchored[0]!, /Visible content/);
  now = 1400;
  await delay(120);
  assert.deepEqual(viewport(), anchored, 'thought folding above the viewport must preserve the visible text');
  now = 2700;
  await delay(120);
  assert.deepEqual(viewport(), anchored, 'tool compaction above the viewport must preserve the visible text');
  backend.emit({type: 'notice', text: 'New output below the viewport'});
  await delay(60);
  assert.deepEqual(viewport(), anchored, 'new output must not move an anchored viewport');
  app.stdin.write('\x1b[1;5F');
  await until(() => app.lastFrame()?.includes('New output below the viewport') ?? false);
  backend.emit({type: 'notice', text: 'Following the latest output again'});
  await until(() => app.lastFrame()?.includes('Following the latest output again') ?? false);
});

test('completed tools show a concise result and expand to reveal full output', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 80, rows: 24}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  backend.emit({type: 'turn_start', text: 'Read the file', files: [], web: false});
  backend.emit({type: 'agent_event', event: {type: 'tool_call_start', agent_id: 'main', parent_agent_id: null,
    data: {call_id: 'read-1', name: 'read', arguments: {path: 'src/app.py'}}}});
  await until(() => app.lastFrame()?.includes('Running') ?? false);
  backend.emit({type: 'agent_event', event: {type: 'tool_call_complete', agent_id: 'main', parent_agent_id: null,
    data: {call_id: 'read-1', success: true, output: 'Full file contents\nSecond line', exit_code: 0}}});
  await until(() => app.lastFrame()?.includes('Read 2 lines · exit 0') ?? false);
  assert.ok(app.lastFrame()?.includes('Done'));
  assert.ok(!app.lastFrame()?.includes('Full file contents'));
  app.stdin.write('\x0f');
  await until(() => app.lastFrame()?.includes('Full file contents') ?? false);
  assert.ok(app.lastFrame()?.includes('path  src/app.py'));
  app.stdin.write('\x0f');
  await until(() => !app.lastFrame()?.includes('Full file contents'));
  backend.emit({type: 'turn_end', status: 'Ready'});
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
});

test('subagents show their live tools inline and in the agent activity view', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 100, rows: 30}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  backend.emit({type: 'turn_start', text: 'Inspect the project', files: [], web: false});
  for (const [id, name, tool, args, progress] of [
    ['a', 'Researcher', 'grep', {pattern: 'auth'}, 'Searching authentication'],
    ['b', 'Reviewer', 'read', {path: 'routes.py'}, 'Reading routes'],
  ] as const) {
    backend.emit({type: 'agent_event', event: {type: 'agent_status', agent_id: id, parent_agent_id: 'main',
      data: {agent_id: id, parent_agent_id: 'main', name, goal: 'Inspect relevant code', depth: 1, status: 'running'}}});
    backend.emit({type: 'agent_event', event: {type: 'tool_call_start', agent_id: id, parent_agent_id: 'main',
      data: {call_id: 'same', name: tool, arguments: args}}});
    backend.emit({type: 'agent_event', event: {type: 'tool_progress', agent_id: id, parent_agent_id: 'main',
      data: {call_id: 'same', content: progress}}});
  }
  await until(() => app.lastFrame()?.includes('Reading routes') ?? false);
  for (const expected of ['Researcher', 'Reviewer', 'grep auth', 'read routes.py', 'Searching authentication']) assert.ok(app.lastFrame()?.includes(expected), expected);
  app.stdin.write('\x07');
  await until(() => app.lastFrame()?.includes('Agent activity') ?? false);
  assert.ok(app.lastFrame()?.includes('Searching authentication'));
  app.stdin.write('\x1b[B');
  await until(() => app.lastFrame()?.includes('Reading routes') ?? false);
  app.stdin.write('\x1b');
  backend.emit({type: 'turn_end', status: 'Ready'});
  await until(() => app.lastFrame()?.includes('completed') ?? false);
});

test('successful tools compact into groups and all detail shortcuts preserve the draft', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 100, rows: 36}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  app.stdin.write('keep my draft');
  await delay(20);
  backend.emit({type: 'turn_start', text: 'Read these files', files: [], web: false});
  for (const index of [1, 2]) {
    backend.emit({type: 'agent_event', event: {type: 'tool_call_start', agent_id: 'main', parent_agent_id: null,
      data: {call_id: `read-${index}`, name: 'read', arguments: {path: `src/file${index}.py`}}}});
    await delay(20);
    backend.emit({type: 'agent_event', event: {type: 'tool_call_complete', agent_id: 'main', parent_agent_id: null,
      data: {call_id: `read-${index}`, success: true, output: `Unique result ${index}`, metadata: {shown_start: 1, shown_end: 1}}}});
  }
  backend.emit({type: 'turn_end', status: 'Ready'});
  await until(() => app.lastFrame()?.includes('Read 2 files') ?? false);
  assert.ok(app.lastFrame()?.includes('src/file1.py'));
  assert.ok(app.lastFrame()?.includes('src/file2.py'));
  await delay(1750);
  await until(() => !app.lastFrame()?.includes('src/file1.py'));
  assert.ok(app.lastFrame()?.includes('Read 2 files'));
  app.stdin.write('\x1bo');
  await until(() => app.lastFrame()?.includes('src/file1.py') ?? false);
  app.stdin.write('\x1ba');
  await until(() => app.lastFrame()?.includes('Unique result 1') && app.lastFrame()?.includes('Unique result 2') || false);
  app.stdin.write('\x1bc');
  await until(() => !app.lastFrame()?.includes('Unique result 1') && !app.lastFrame()?.includes('src/file1.py'));
  app.stdin.write('\x0f');
  await until(() => app.lastFrame()?.includes('Unique result 2') ?? false);
  assert.ok(!app.lastFrame()?.includes('Unique result 1'));
  assert.ok(app.lastFrame()?.includes('keep my draft'));
});

for (const [index, [mode, label, display]] of approvalModes.entries()) {
  test(`approval picker displays Python's ${label} label after selecting ${mode}`, async () => {
    const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 100, rows: 30}}/>);
    await until(() => app.lastFrame()?.includes('Ask ▾') ?? false);
    for (let tab = 0; tab < 3; tab++) { app.stdin.write('\t'); await delay(20); }
    app.stdin.write('\r');
    await until(() => app.lastFrame()?.includes('Choose an approval mode') ?? false);
    for (let down = 0; down < index; down++) { app.stdin.write('\x1b[B'); await delay(20); }
    app.stdin.write('\r');
    await until(() => backend.requests.some(request => request.method === 'approval'));
    assert.deepEqual(backend.requests.find(request => request.method === 'approval')!.params, {mode});
    await until(() => !app.lastFrame()?.includes('Choose an approval mode'));
    await until(() => app.lastFrame()?.includes(`${display} ▾`) ?? false);
    assert.ok(app.lastFrame()?.includes(`Ready · ${label}`));
  });
}

test('approval picker preserves the draft and command completion is keyboard accessible', async () => {
  const backend = new Backend(), app = render(<PostalApp backend={backend} size={{columns: 100, rows: 30}}/>);
  await until(() => app.lastFrame()?.includes('Ready') ?? false);
  app.stdin.write('keep my draft');
  await delay(30);
  for (let index = 0; index < 3; index++) { app.stdin.write('\t'); await delay(20); }
  app.stdin.write('\r');
  await until(() => app.lastFrame()?.includes('Choose an approval mode') ?? false);
  assert.ok(app.lastFrame()?.includes('Auto-edit'));
  app.stdin.write('\x1b[B'); await delay(20);
  await until(() => app.lastFrame()?.includes('On fail') ?? false);
  app.stdin.write('\r');
  await until(() => backend.requests.some(request => request.method === 'approval'));
  assert.deepEqual(backend.requests.find(request => request.method === 'approval')!.params, {mode: 'on_fail'});
  await until(() => app.lastFrame()?.includes('keep my draft') ?? false);
  app.stdin.write('\x10');
  await until(() => app.lastFrame()?.includes('Commands') ?? false);
  app.stdin.write('he'); await delay(20);
  app.stdin.write('\t');
  await until(() => app.lastFrame()?.includes('/help ') ?? false);
  app.stdin.write('\x1b');
});
