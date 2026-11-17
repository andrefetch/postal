import assert from 'node:assert/strict';
import {test} from 'node:test';
import {renderToString} from 'ink';
import stripAnsi from 'strip-ansi';
import stringWidth from 'string-width';
import ToolRow, {toolSummary, type ToolActivity} from '../src/ToolRow.js';
import {initialState, reduce} from '../src/state.js';
import {conversationLines} from '../src/components.js';

const tool: ToolActivity = {name: 'read', args: {path: 'src/app.py'}, status: 'completed', output: 'first\nsecond', startedAt: 1000, finishedAt: 1800};

test('tool rows fit narrow terminals and distinguish successful, failed, and stopped calls', () => {
  for (const width of [26, 40, 80]) for (const [status, label] of [['running', 'Running'], ['completed', 'Done'], ['failed', 'Failed'], ['cancelled', 'Stopped']]) {
    const frame = stripAnsi(renderToString(<ToolRow tool={{activity: {...tool, status: status!, args: {path: 'src/a-very-long-file-name/with-unicode-📦.py'}}}} width={width} now={1800} animate/>, {columns: width}));
    assert.equal(frame.split('\n').length, 1);
    assert.ok(stringWidth(frame) <= width, frame);
    assert.ok(frame.includes(label!), frame);
    if (width === 80) assert.ok(frame.includes('0.8s'));
  }
  assert.equal(toolSummary(tool), 'Read 2 lines');
  assert.equal(toolSummary({...tool, exitCode: 0}), 'Read 2 lines · exit 0');
  assert.equal(toolSummary({...tool, name: 'edit', diff: '--- a/x\n+++ b/x\n-old\n+new\n+next'}), '+2 −1');
  assert.equal(toolSummary({...tool, status: 'failed', error: 'Permission denied\nDetails'}), 'Permission denied');
  assert.equal(toolSummary({...tool, status: 'cancelled'}), 'Stopped before completion');
  assert.equal(toolSummary({...tool, status: 'running'}), 'second');
});

test('completion records frozen timing and keeps full results behind expansion', t => {
  let now = 1000;
  t.mock.method(Date, 'now', () => now);
  let state = reduce(initialState, {type: 'agent_event', event: {type: 'tool_call_start', agent_id: 'main', parent_agent_id: null,
    data: {call_id: 'call', name: 'read', arguments: {path: 'src/app.py'}}}});
  now = 1800;
  state = reduce(state, {type: 'agent_event', event: {type: 'tool_call_complete', agent_id: 'main', parent_agent_id: null,
    data: {call_id: 'call', success: true, output: 'Full result\nSecond line', exit_code: null}}});
  assert.equal(state.blocks[0]!.startedAt, 1000);
  assert.equal(state.blocks[0]!.finishedAt, 1800);
  assert.equal(state.blocks[0]!.exitCode, undefined);
  const collapsed = conversationLines(state.blocks, 60, new Set());
  assert.ok(collapsed.some(line => line.tool?.activity.status === 'completed'));
  assert.ok(collapsed.some(line => line.text.includes('Read 2 lines')));
  assert.ok(!collapsed.some(line => line.text.includes('Full result')));
  const expanded = conversationLines(state.blocks, 60, new Set([0]));
  assert.ok(expanded.some(line => line.text.includes('path  src/app.py')));
  assert.ok(expanded.some(line => line.text.includes('Full result')));
});
