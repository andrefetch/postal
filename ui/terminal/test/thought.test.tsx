import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {setTimeout as delay} from 'node:timers/promises';
import {renderToString} from 'ink';
import {render, cleanup} from 'ink-testing-library';
import stripAnsi from 'strip-ansi';
import stringWidth from 'string-width';
import ThoughtLine, {thoughtBreath, thoughtShimmer} from '../src/ThoughtLine.js';
import {conversationLines} from '../src/components.js';

afterEach(cleanup);

test('thought header stays compact and breathing and shimmer stay grayscale', () => {
  for (const width of [26, 40, 80]) {
    const frame = stripAnsi(renderToString(<ThoughtLine width={width} elapsed={2.4} steps={['Actual trace']} headOnly/>, {columns: width}));
    assert.equal(frame.split('\n').length, 1);
    assert.ok(stringWidth(frame) <= width);
    assert.ok(frame.includes('✦ Thinking… 2.4s'));
    assert.ok(!/[\u2800-\u28ff]/.test(frame), 'thinking should use a sparkle, not the tool lattice');
  }
  assert.equal(thoughtBreath(0), 0.55);
  assert.equal(thoughtBreath(0.8), 1);
  assert.notEqual(thoughtShimmer(0, 8, 0), thoughtShimmer(0, 8, 0.5));
  assert.match(thoughtShimmer(0, 8, 0.5), /^#([\da-f]{2})\1\1$/i);
});

test('settling freezes the timer, collapses the trace, and calls onSettle once', async () => {
  const settled: number[] = [];
  const props = {steps: ['Reading supplied reasoning', 'Checking the answer'], elapsed: 2.4, onSettle: (seconds: number) => settled.push(seconds)};
  const app = render(<ThoughtLine {...props}/>);
  await delay(30);
  assert.ok(app.lastFrame()?.includes('Checking the answer'));
  app.rerender(<ThoughtLine {...props} working={false}/>);
  await delay(40);
  assert.ok(app.lastFrame()?.includes('Thought for 2.4s'));
  assert.ok(!app.lastFrame()?.includes('Checking the answer'));
  app.rerender(<ThoughtLine {...props} working={false}/>);
  await delay(40);
  assert.deepEqual(settled, [2.4]);
});

test('reasoning traces open while working, collapse on settlement, and can reopen', () => {
  const working = {id: 1, kind: 'reasoning' as const, text: 'First actual step\nSecond actual step', status: 'running', startedAt: 1000};
  const running = conversationLines([working], 60, new Set());
  assert.ok(running[0]!.thought?.open);
  assert.ok(running.some(line => line.text.includes('• Second actual step')));
  assert.equal(conversationLines([working], 60, new Set([-2])).length, 1);
  const complete = {...working, status: 'completed', finishedAt: 3400};
  const collapsed = conversationLines([complete], 60, new Set([-2]));
  assert.equal(collapsed.length, 1);
  assert.equal(collapsed[0]!.text, 'Thought for');
  assert.equal(collapsed[0]!.thought?.finishedAt, 3400);
  assert.ok(conversationLines([complete], 60, new Set([1])).some(line => line.text.includes('✓ Second actual step')));
});
