import assert from 'node:assert/strict';
import {test} from 'node:test';
import {renderToString} from 'ink';
import stripAnsi from 'strip-ansi';
import stringWidth from 'string-width';
import ToolRow from '../src/ToolRow.js';
import {conversationLines} from '../src/components.js';
import {initialState, reduce, type Block} from '../src/state.js';
import {conversationToolGroups, expandTools} from '../src/toolNavigation.js';
import {agentToolKey, closedGroupKey, groupTools, shortPath, toolDiffPreview, toolSummary, TOOL_COMPACT_DELAY, type DetailKey, type ToolActivity} from '../src/toolPresentation.js';

const base: ToolActivity = {name: 'read', args: {path: 'src/app.py'}, status: 'completed', output: 'header\n1|one\n2|two', startedAt: 1000, finishedAt: 2000};
const block = (id: number, name = 'read', extra: Partial<Block> = {}): Block => ({id, kind: 'tool', title: name, args: {path: `src/file${id}.py`},
  status: 'completed', text: `contents-${id}`, startedAt: 1000 + id * 100, finishedAt: 2000, ...extra});
const context = (now: number) => ({busy: false, status: 'Ready', agents: {}, now});

test('result summaries use real metadata, preserve zero counts, and recognize test results', () => {
  assert.equal(toolSummary({...base, metadata: {shown_start: 5, shown_end: 52, total_lines: 100}}), 'Read 48 lines');
  assert.equal(toolSummary({...base, metadata: {lines: 0}, output: 'File is empty.'}), 'Read 0 lines');
  assert.equal(toolSummary({...base, metadata: {shown_start: 8, shown_end: 7}}), 'Read 0 lines');
  assert.equal(toolSummary({...base, name: 'grep', metadata: {matches: 6, files_searched: 12}}), 'Found 6 matches · 12 files searched');
  assert.equal(toolSummary({...base, name: 'grep', metadata: {matches: 1}}), 'Found 1 match');
  assert.equal(toolSummary({...base, name: 'glob', metadata: {matches: 0}}), 'Found 0 files');
  assert.equal(toolSummary({...base, name: 'bash', output: '3 passed in 0.12s', exitCode: 0}), '3 tests passed · exit 0');
  assert.ok(!toolSummary({...base, name: 'bash', output: '3 passed, 1 failed'}).includes('tests passed'));
  assert.equal(toolSummary({...base, name: 'write', metadata: {lines: 4, is_new_file: true}}), 'Created 4 lines');
  assert.ok(toolSummary({...base, truncated: true}).endsWith('output truncated'));
  const diff = toolDiffPreview('--- a/x\n+++ b/x\n@@ -1 +1 @@\n--- old comment\n+++ new comment');
  assert.equal(diff.added, 1);
  assert.equal(diff.removed, 1);
});

test('live previews reserve two rows, edit previews fold, and errors stay visible', () => {
  const running = block(1, 'bash', {status: 'running', finishedAt: undefined, text: ''});
  const first = conversationLines([running], 60, new Set(), context(2100));
  const progress = conversationLines([{...running, text: 'old\nrecent\nlatest'}], 60, new Set(), context(2100));
  assert.equal(first.length, 3);
  assert.equal(progress.length, 3);
  assert.ok(first[1]!.text.includes('Waiting for output'));
  assert.ok(progress[1]!.text.includes('recent') && progress[2]!.text.includes('latest'));
  assert.ok(!progress.some(line => line.text.includes('old')));
  const edit = block(2, 'edit', {diff: '--- a/x\n+++ b/x\n-old\n+new\n+another\n+last', output: '', metadata: {replaced_count: 1}});
  const fresh = conversationLines([edit], 70, new Set(), context(2200));
  assert.ok(fresh.some(line => line.text.includes('-old')));
  assert.ok(fresh.some(line => line.text.includes('+new')));
  assert.ok(fresh.some(line => line.text.includes('1 more changed line')));
  const compact = conversationLines([edit], 70, new Set(), context(2000 + TOOL_COMPACT_DELAY));
  assert.equal(compact.length, 1);
  assert.equal(compact[0]!.tool!.compact, true);
  const full = conversationLines([edit], 70, new Set([2]), context(10000));
  assert.ok(full.some(line => line.text.includes('+last')));
  const error = block(3, 'bash', {status: 'failed', error: 'Traceback (most recent call last):\n  File "x.py"\nPermissionError: access denied'});
  const failed = conversationLines([error], 70, new Set(), context(100000));
  assert.ok(failed.some(line => line.text.includes('PermissionError: access denied')));
  assert.equal(failed[0]!.tool!.compact, false);
});

test('read/search groups retain individual calls and never swallow failures or unrelated calls', () => {
  const blocks = [block(1), block(2), block(3, 'bash'), block(4, 'grep'), block(5, 'glob')];
  const groups = conversationToolGroups(blocks, {});
  assert.equal(groups.length, 3);
  assert.equal(groups[0]!.activity.name, 'Read 2 files');
  assert.equal(groups[2]!.activity.name, '2 searches');
  const collapsed = conversationLines(blocks, 80, new Set(), context(10000));
  assert.equal(collapsed.filter(line => line.group).length, 2);
  assert.ok(!collapsed.some(line => line.text.includes('src/file1.py')));
  const expanded = conversationLines(blocks, 80, new Set<DetailKey>([groups[0]!.key]), context(10000));
  assert.ok(expanded.some(line => line.text.includes('src/file1.py')));
  assert.ok(expanded.some(line => line.text.includes('src/file2.py')));
  const failure = [block(1), block(2, 'read', {status: 'failed', error: 'Permission denied'})];
  const group = conversationToolGroups(failure, {})[0]!;
  const hidden = conversationLines(failure, 80, new Set<DetailKey>([closedGroupKey(group.key)]), context(10000));
  assert.ok(hidden.some(line => line.text.includes('Permission denied')));
  assert.ok(hidden.some(line => line.tool?.activity.status === 'failed'));
  const searches = groupTools([{key: agentToolKey('a', 'same'), activity: {...base, name: 'grep'}}, {key: agentToolKey('a', 'second'), activity: {...base, name: 'glob'}}], 'a');
  assert.notEqual(searches[0]!.key, groupTools([{key: agentToolKey('b', 'same'), activity: base}, {key: agentToolKey('b', 'second'), activity: base}], 'b')[0]!.key);
});

test('filenames survive long paths and status columns stay fixed across tool states', () => {
  const path = '/workspace/very-long-project/deeply/nested/directory/ImportantFile.ts';
  assert.ok(shortPath(path, 24).endsWith('ImportantFile.ts'));
  assert.ok(shortPath(path, 24).includes('…'));
  assert.ok(stringWidth(shortPath('src/unicode-📦-filename.ts', 12)) <= 12);
  const positions: number[] = [];
  for (const status of ['running', 'completed', 'failed', 'cancelled']) {
    const label = status === 'running' ? 'Running' : status === 'completed' ? 'Done' : status === 'failed' ? 'Failed' : 'Stopped';
    const frame = stripAnsi(renderToString(<ToolRow tool={{activity: {...base, status, args: {path}}}} width={80} now={2200} animate/>, {columns: 80}));
    assert.equal(stringWidth(frame), 80);
    assert.ok(frame.includes('ImportantFile.ts'));
    positions.push(stringWidth(frame.slice(0, frame.indexOf(label))));
  }
  assert.equal(new Set(positions).size, 1);
});

test('latest, group, expand-all, and collapse-all navigate the same tool groups', () => {
  const state = {...initialState, blocks: [block(1), block(2)]};
  const group = conversationToolGroups(state.blocks, {})[0]!;
  const all = expandTools('all', state, new Set());
  assert.ok(all.has(1) && all.has(2) && all.has(group.key));
  const none = expandTools('none', state, all);
  assert.ok(!none.has(1) && !none.has(2) && none.has(closedGroupKey(group.key)));
  const latest = expandTools('latest', state, none);
  assert.ok(latest.has(2) && latest.has(group.key) && !latest.has(1));
  const closed = expandTools('group', state, latest);
  assert.ok(closed.has(closedGroupKey(group.key)));
  const reopened = expandTools('group', state, closed);
  assert.ok(reopened.has(group.key));
});

test('completion metadata reaches both main and subagent summaries', () => {
  let state = initialState;
  for (const agent_id of ['main', 'child']) {
    state = reduce(state, {type: 'agent_event', event: {agent_id, parent_agent_id: agent_id === 'main' ? null : 'main', type: 'tool_call_start', data: {call_id: 'same', name: 'grep', arguments: {pattern: 'auth'}}}});
    state = reduce(state, {type: 'agent_event', event: {agent_id, parent_agent_id: agent_id === 'main' ? null : 'main', type: 'tool_call_complete', data: {call_id: 'same', success: true, output: 'auth match', metadata: {matches: 6}, truncated: true}}});
  }
  assert.equal(state.blocks[0]!.metadata!.matches, 6);
  assert.equal(state.agents.child!.tools[0]!.metadata!.matches, 6);
  assert.ok(toolSummary(state.agents.child!.tools[0]!).includes('Found 6 matches'));
});

test('successful completion settles the lattice into a checkmark without changing elapsed time', t => {
  let now = 2050;
  t.mock.method(Date, 'now', () => now);
  const first = stripAnsi(renderToString(<ToolRow tool={{activity: base}} width={80} now={now} animate/>, {columns: 80}));
  assert.match(first, /^[\u2800-\u28ff]{2}/);
  assert.ok(first.includes('1.0s'));
  now = 2700;
  const settled = stripAnsi(renderToString(<ToolRow tool={{activity: base}} width={80} now={now} animate/>, {columns: 80}));
  assert.ok(settled.startsWith('✓'));
  assert.ok(settled.includes('1.0s'));
});
