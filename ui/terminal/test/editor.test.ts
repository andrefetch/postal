import assert from 'node:assert/strict';
import {test} from 'node:test';
import stringWidth from 'string-width';
import {clean, edit, insert, visualLines, cursorRow} from '../src/editor.js';

test('editing respects emoji graphemes and removes terminal control sequences', () => {
  let draft = insert({text: '', cursor: 0}, 'A👨‍👩‍👧‍👦界');
  draft = edit(draft, '', {leftArrow: true}, 30);
  draft = edit(draft, '', {backspace: true}, 30);
  assert.equal(draft.text, 'A界');
  assert.equal(draft.cursor, 1);
  assert.equal(clean('\x1b[2Jsafe\x00\x07'), 'safe');
});
test('pasted lines wrap within the terminal and preserve the cursor position', () => {
  const draft = insert({text: '', cursor: 0}, 'alpha\r\n界界界界界\nlast');
  const lines = visualLines(draft.text, 6);
  assert.ok(lines.every(line => stringWidth(line.text) <= 6));
  assert.equal(lines[cursorRow(lines, draft.cursor)]!.text, 'last');
  const previous = edit(draft, '', {upArrow: true}, 6);
  assert.ok(previous.cursor < draft.cursor);
  assert.equal(draft.text, 'alpha\n界界界界界\nlast');
});
test('the cursor has a visible line at an exact wrap boundary', () => {
  const lines = visualLines('123456', 6);
  assert.equal(cursorRow(lines, 6), 1);
  assert.equal(lines[1]!.text, '');
});
