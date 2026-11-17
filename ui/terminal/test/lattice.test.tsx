import assert from 'node:assert/strict';
import {test} from 'node:test';
import {renderToString} from 'ink';
import stripAnsi from 'strip-ansi';
import LatticeLoader, {formatElapsed, latticeOpacity} from '../src/LatticeLoader.js';
import {conversationLines} from '../src/components.js';
import {initialState, reduce} from '../src/state.js';

test('arrow cells follow the supplied CSS delays and opacity keyframes', () => {
  assert.equal(latticeOpacity(3, 0), 0.14);
  assert.equal(latticeOpacity(0, 0.05), 0.14);
  assert.equal(latticeOpacity(3, 0.2), 1);
  assert.equal(latticeOpacity(3, 0.5), 0.14);
  assert.notEqual(latticeOpacity(3, 0.2), latticeOpacity(2, 0.2));
  assert.ok(Math.abs(latticeOpacity(3, 0.2) - latticeOpacity(3, 0.92)) < 0.001);
});

test('lattice displays its grid, working timer, and frozen success or failure labels', () => {
  for (const [status, label] of [['working', 'Thinking'], ['done', 'Done in'], ['error', 'Failed after']] as const) {
    const text = stripAnsi(renderToString(<LatticeLoader status={status} elapsed={2.4}/>, {columns: 40}));
    assert.equal(text.split('\n').length, 3);
    assert.equal([...text].filter(character => character === '●').length, 9);
    assert.ok(text.includes(`${label} 2.4s`));
  }
  assert.equal(formatElapsed(65.2), '1m 5.2s');
  assert.equal(formatElapsed(-1), '0.0s');
  const lines = conversationLines([{id: 1, kind: 'reasoning', status: 'completed', text: '', startedAt: 1000, finishedAt: 3400}], 40, new Set());
  assert.equal(lines.length, 3);
  assert.ok(lines.every(line => line.lattice?.status === 'done' && line.lattice.finishedAt === 3400));
});

test('reasoning failure freezes the lattice timer at disconnection', () => {
  let state = reduce(initialState, {type: 'turn_start', text: 'Inspect', files: [], web: false});
  state = reduce(state, {type: 'agent_event', event: {type: 'reasoning_delta', agent_id: 'main', parent_agent_id: null, data: {content: 'Working'}}});
  state = reduce(state, {type: 'fatal', message: 'Connection lost'});
  assert.equal(state.busy, false);
  const lines = conversationLines(state.blocks, 40, new Set(), state).filter(line => line.lattice);
  assert.equal(lines.length, 3);
  assert.ok(lines.every(line => line.lattice!.status === 'error' && line.lattice!.finishedAt !== undefined));
});
