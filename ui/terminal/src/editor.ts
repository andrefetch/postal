import stringWidth from 'string-width';
import stripAnsi from 'strip-ansi';
import type {Key} from 'ink';

export interface Draft {text: string; cursor: number}
export interface VisualLine {text: string; start: number; end: number}
const segments = new Intl.Segmenter(undefined, {granularity: 'grapheme'});
export const clean = (text: string) => stripAnsi(text).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/g, '');
export const emptyDraft = (): Draft => ({text: '', cursor: 0});
export function insert(draft: Draft, value: string): Draft {
  value = clean(value.replace(/\r\n?/g, '\n')).replace(/\t/g, '  ');
  return {text: draft.text.slice(0, draft.cursor) + value + draft.text.slice(draft.cursor), cursor: draft.cursor + value.length};
}
function boundaries(text: string) { return [...segments.segment(text)].map(part => part.index).concat(text.length); }
export function visualLines(text: string, width: number): VisualLine[] {
  width = Math.max(1, width);
  const lines: VisualLine[] = [];
  let start = 0, row = '', cells = 0;
  for (const part of segments.segment(text)) {
    if (part.segment === '\n') {
      lines.push({text: row, start, end: part.index});
      start = part.index + 1; row = ''; cells = 0;
    } else {
      const size = stringWidth(part.segment);
      if (cells + size > width && row) {
        lines.push({text: row, start, end: part.index});
        start = part.index; row = ''; cells = 0;
      }
      row += part.segment; cells += size;
    }
  }
  lines.push({text: row, start, end: text.length});
  if (cells >= width) lines.push({text: '', start: text.length, end: text.length});
  return lines;
}
export function cursorRow(lines: VisualLine[], cursor: number) {
  return Math.max(0, lines.findLastIndex(line => line.start <= cursor));
}
export function edit(draft: Draft, input: string, key: Partial<Key>, width: number): Draft {
  const {text, cursor} = draft;
  const points = boundaries(text);
  const previous = points.findLast(point => point < cursor) ?? 0;
  const next = points.find(point => point > cursor) ?? text.length;
  if (key.leftArrow) return {...draft, cursor: previous};
  if (key.rightArrow) return {...draft, cursor: next};
  if (key.home || (key.ctrl && input === 'a')) return {...draft, cursor: text.lastIndexOf('\n', cursor - 1) + 1};
  if (key.end || (key.ctrl && input === 'e')) {
    const end = text.indexOf('\n', cursor);
    return {...draft, cursor: end < 0 ? text.length : end};
  }
  if (key.backspace || input === '\u007f') return {text: text.slice(0, previous) + text.slice(cursor), cursor: previous};
  if (key.delete) return {text: text.slice(0, cursor) + text.slice(next), cursor};
  if (key.ctrl && input === 'u') return {text: text.slice(cursor), cursor: 0};
  if (key.ctrl && input === 'k') return {text: text.slice(0, cursor), cursor};
  if (key.ctrl && input === 'w') {
    const before = text.slice(0, cursor).replace(/\s*\S+\s*$/, '');
    return {text: before + text.slice(cursor), cursor: before.length};
  }
  if (key.upArrow || key.downArrow) {
    const lines = visualLines(text, width), row = cursorRow(lines, cursor);
    const target = lines[Math.max(0, Math.min(lines.length - 1, row + (key.upArrow ? -1 : 1)))];
    const column = stringWidth(text.slice(lines[row]!.start, cursor));
    let offset = target!.start, cells = 0;
    for (const part of segments.segment(target!.text)) {
      if (cells + stringWidth(part.segment) > column) break;
      cells += stringWidth(part.segment); offset += part.segment.length;
    }
    return {...draft, cursor: offset};
  }
  if (!key.ctrl && !key.meta && !key.escape && !key.return && !key.tab && input) return insert(draft, input);
  return draft;
}
export function fit(text: string, width: number) {
  text = clean(text).replace(/\s+/g, ' ');
  if (stringWidth(text) <= width) return text;
  let result = '';
  for (const part of segments.segment(text)) {
    if (stringWidth(result + part.segment) > Math.max(0, width - 1)) break;
    result += part.segment;
  }
  return width > 0 ? result + '…' : '';
}
