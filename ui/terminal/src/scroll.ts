import {useCallback, useLayoutEffect, useState, type SetStateAction} from 'react';
import type {ConversationLine} from './components.js';

export function anchoredScroll(previous: ConversationLine[], current: ConversationLine[], offset: number, height: number) {
  const max = Math.max(0, current.length - height);
  if (previous === current) return Math.max(0, Math.min(max, offset));
  const positions = new Map(current.map((line, index) => [line.key, index]));
  // Prefer the top visible row. If it disappeared, keep the next surviving row
  // in its screen position; fall back to an earlier row when the tail vanished.
  for (let index = offset; index < previous.length; index++) {
    const next = positions.get(previous[index]!.key);
    if (next !== undefined) return Math.max(0, Math.min(max, next - (index - offset)));
  }
  for (let index = Math.min(offset - 1, previous.length - 1); index >= 0; index--) {
    const next = positions.get(previous[index]!.key);
    if (next !== undefined) return Math.max(0, Math.min(max, next - (index - offset)));
  }
  return Math.max(0, Math.min(max, offset));
}

export function useConversationScroll(lines: ConversationLine[], height: number) {
  const [position, setPosition] = useState<{lines: ConversationLine[]; offset: number} | null>(null);
  const scroll = position === null ? null : anchoredScroll(position.lines, lines, position.offset, height);
  // Derive the anchored offset before painting, then retain only the latest rows.
  useLayoutEffect(() => {
    if (position !== null && (position.lines !== lines || position.offset !== scroll)) setPosition({lines, offset: scroll!});
  }, [lines, position, scroll]);
  const setScroll = useCallback((update: SetStateAction<number | null>) => setPosition(previous => {
    const current = previous === null ? null : anchoredScroll(previous.lines, lines, previous.offset, height);
    const offset = typeof update === 'function' ? update(current) : update;
    return offset === null ? null : {lines, offset};
  }), [lines, height]);
  return [scroll, setScroll] as const;
}
