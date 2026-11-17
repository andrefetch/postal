import assert from 'node:assert/strict';
import {test} from 'node:test';
import {conversationLines} from '../src/components.js';
import {anchoredScroll} from '../src/scroll.js';
import type {Block} from '../src/state.js';

test('row anchors survive simultaneous compaction and appended content', () => {
  const blocks: Block[] = [
    {id: 0, kind: 'reasoning', text: 'First\nSecond\nThird\nFourth', status: 'completed', startedAt: 0, finishedAt: 1000},
    ...[1, 2].map(id => ({id, kind: 'tool' as const, title: 'read', text: 'Result', args: {path: `file${id}`}, status: 'completed', finishedAt: 1000})),
    {id: 3, kind: 'notice', text: Array.from({length: 30}, (_, i) => `Repeated text ${i % 3}`).join('\n')},
    {id: 4, kind: 'notice', text: Array.from({length: 30}, (_, i) => `Repeated text ${i % 3}`).join('\n')},
  ];
  const context = {busy: false, status: 'Ready', agents: {}, now: 1000};
  const before = conversationLines(blocks, 60, new Set(), context);
  const after = conversationLines([...blocks, {id: 5, kind: 'notice', text: 'new\n'.repeat(20)}], 60, new Set(), {...context, now: 3000});
  const offset = before.findIndex(line => line.key.startsWith('block:4:')) + 10;
  const next = anchoredScroll(before, after, offset, 10);
  assert.notEqual(next, offset);
  assert.deepEqual(after.slice(next, next + 10).map(line => line.key), before.slice(offset, offset + 10).map(line => line.key));
  for (const lines of [before, after]) assert.equal(new Set(lines.map(line => line.key)).size, lines.length);
});

test('removed anchors fall back to surviving rows and offsets clamp to the viewport', () => {
  const rows = ['a', 'b', 'c', 'd', 'e', 'f'].map(key => ({key, text: key}));
  const current = [rows[0]!, ...rows.slice(3)];
  assert.equal(anchoredScroll(rows, current, 2, 2), 0, 'next surviving row retains its screen position');
  assert.equal(anchoredScroll(rows, rows.slice(0, 3), 4, 2), 1, 'when the tail disappears, use an earlier survivor');
  assert.equal(anchoredScroll(rows, rows, 4, 5), 1, 'a taller viewport clamps the old offset');
  assert.equal(anchoredScroll(rows, [], 4, 2), 0);
});
