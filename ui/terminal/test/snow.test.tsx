import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {setTimeout as delay} from 'node:timers/promises';
import {render, cleanup} from 'ink-testing-library';
import stringWidth from 'string-width';
import {Box} from 'ink';
import PixelSnow, {snowFrame} from '../src/PixelSnow.js';

afterEach(cleanup);

test('snow drifts within terminal bounds and never enters protected content', () => {
  const exclusions = [{x: 20, y: 4, width: 40, height: 15}];
  const props = {columns: 80, rows: 24, exclusions, intro: false};
  const first = snowFrame(props, 0), later = snowFrame(props, 2);
  assert.ok(first.length > 0);
  assert.notDeepEqual(first, later);
  assert.deepEqual(first, snowFrame(props, 0));
  for (const cell of [...first, ...later]) {
    assert.ok(cell.x >= 0 && cell.x < 80 && cell.y >= 0 && cell.y < 24);
    assert.ok(!(cell.x >= 20 && cell.x < 60 && cell.y >= 4 && cell.y < 19));
    assert.equal(stringWidth(cell.character), 1);
    assert.match(cell.color, /^#([\da-f]{2})\1\1$/i);
    assert.ok(parseInt(cell.color.slice(1, 3), 16) < 90, 'snow should stay dimmer than interface text');
  }
  assert.ok(snowFrame({columns: 1000, rows: 1000, intro: false}, 2).length <= 160);
});

test('intro and zero intensity settings keep the background clear', () => {
  const props = {columns: 80, rows: 24};
  assert.deepEqual(snowFrame(props, 0), []);
  assert.ok(snowFrame(props, 1.4).length > 0);
  for (const disabled of [{density: 0}, {brightness: 0}, {opacity: 0}]) assert.deepEqual(snowFrame({...props, ...disabled}, 2), []);
  assert.deepEqual(snowFrame({...props, exclusions: [{x: 0, y: 0, width: 80, height: 24}]}, 2), []);
});

test('snow pauses without moving and refits resized terminals', async () => {
  const snow = (columns: number, rows: number, paused = false) => <Box width={columns} height={rows}><PixelSnow columns={columns} rows={rows} intro={false} paused={paused}/></Box>;
  const view = render(snow(80, 24));
  const first = view.lastFrame();
  await delay(250);
  assert.notEqual(view.lastFrame(), first);
  view.rerender(snow(80, 24, true));
  await delay(40);
  const paused = view.lastFrame();
  await delay(200);
  assert.equal(view.lastFrame(), paused);
  view.rerender(snow(40, 12, true));
  await delay(40);
  const lines = (view.lastFrame() ?? '').split('\n');
  assert.ok(lines.length <= 12);
  assert.ok(lines.every(line => stringWidth(line) <= 40));
});
