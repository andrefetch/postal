import assert from 'node:assert/strict';
import {test} from 'node:test';
import {shimmerColor} from '../src/activity.js';
import {colors, conversationLines} from '../src/components.js';
import {initialState, reduce} from '../src/state.js';

test('palette and animated text stay grayscale while the gradient moves', () => {
  for (const color of Object.values(colors)) assert.match(color, /^#([\da-f]{2})\1\1$/i);
  const shades = Array.from({length: 40}, (_, frame) => shimmerColor(0, frame, 8));
  for (const color of shades) assert.match(color, /^#([\da-f]{2})\1\1$/i);
  assert.ok(shades.some(color => parseInt(color.slice(1, 3), 16) > 240));
  assert.ok(shades.some(color => parseInt(color.slice(1, 3), 16) < 24));
  assert.notEqual(shimmerColor(0, 0, 8), shimmerColor(0, 4, 8));
  assert.notEqual(shimmerColor(0, 4, 8), shimmerColor(3, 4, 8));
  assert.equal(shimmerColor(0, 4, 8), shimmerColor(0, 29, 8));
});

test('reasoning animates only until completion and replies are labeled Postal', () => {
  let state = reduce(initialState, {type: 'turn_start', text: 'hello', files: [], web: false});
  state = reduce(state, {type: 'agent_event', event: {type: 'reasoning_delta', agent_id: 'main', parent_agent_id: null, data: {content: 'Considering'}}});
  assert.ok(conversationLines(state.blocks, 40, new Set()).some(line => line.activity && line.text.includes('Thinking')));
  state = reduce(state, {type: 'agent_event', event: {type: 'reasoning_complete', agent_id: 'main', parent_agent_id: null, data: {}}});
  assert.ok(conversationLines(state.blocks, 40, new Set()).every(line => !line.activity));
  const lines = conversationLines([{id: 1, kind: 'assistant', text: '# Heading\n\n**Bold** and `code` [link](https://example.com)\n\n```js\nconst x = 1;\n```\n\n> Quote\n\n| Name | Value |\n| --- | --- |\n| A | 1 |'}], 80, new Set());
  assert.equal(lines[0]!.text, 'Postal');
  assert.ok(!lines.map(line => line.text).join('\n').match(/\x1b\[(?:3[1-6]|9[1-6]|38;[25];)/));
});
