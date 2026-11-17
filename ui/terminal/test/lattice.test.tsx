import assert from 'node:assert/strict';
import {test} from 'node:test';
import {renderToString} from 'ink';
import stripAnsi from 'strip-ansi';
import LatticeLoader, {formatElapsed, latticeOpacity, latticeGlyphs} from '../src/LatticeLoader.js';
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
    assert.equal(text.split('\n').length, 1);
    assert.equal([...text].filter(character => /[\u2800-\u28ff]/.test(character)).length, 2);
    assert.ok(text.includes(`${label} 2.4s`));
  }
  assert.equal(formatElapsed(65.2), '1m 5.2s');
  assert.equal(formatElapsed(-1), '0.0s');
  const lines = conversationLines([{id: 1, kind: 'reasoning', status: 'completed', text: '', startedAt: 1000, finishedAt: 3400}], 40, new Set());
  assert.equal(lines.length, 1);
  assert.ok(lines.every(line => line.thought?.status === 'done' && line.thought.finishedAt === 3400));
});

test('reasoning failure freezes the thought timer at disconnection', () => {
  let state = reduce(initialState, {type: 'turn_start', text: 'Inspect', files: [], web: false});
  state = reduce(state, {type: 'agent_event', event: {type: 'reasoning_delta', agent_id: 'main', parent_agent_id: null, data: {content: 'Working'}}});
  state = reduce(state, {type: 'fatal', message: 'Connection lost'});
  assert.equal(state.busy, false);
  const lines = conversationLines(state.blocks, 40, new Set(), state).filter(line => line.thought);
  assert.equal(lines.length, 1);
  assert.ok(lines.every(line => line.thought!.status === 'error' && line.thought!.finishedAt !== undefined));
});

test('compact lattice occupies two columns and animates using the arrow pattern', () => {
  const frames = [0, 0.1, 0.2, 0.3, 0.4].map(time => latticeGlyphs(time).map(cell => cell.character).join(''));
  assert.ok(frames.every(frame => [...frame].length === 2));
  assert.ok(new Set(frames).size > 2);
});
