import assert from 'node:assert/strict';
import {test} from 'node:test';
import {PassThrough} from 'node:stream';
import {terminalInput, type MouseEvent} from '../src/mouse.js';
test('mouse reports are kept out of the prompt, including split reports', () => {
  const source = new PassThrough();
  const input = terminalInput(source as unknown as NodeJS.ReadStream);
  const events: MouseEvent[] = [], text: string[] = [];
  input.events.on('mouse', event => events.push(event));
  input.stream.on('data', chunk => text.push(chunk.toString()));
  source.write('hello\x1b[<0;');
  source.write('20;16Mworld');
  source.write('\x1b[<0;20;16m');
  assert.deepEqual(events, [{x: 19, y: 15, button: 0}]);
  assert.equal(text.join(''), 'helloworld');
  input.dispose();
});
