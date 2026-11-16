import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';
import {StringDecoder} from 'node:string_decoder';
import {createContext, useContext, useEffect, useRef} from 'react';
import {Box, measureElement, type DOMElement, type BoxProps} from 'ink';
export interface MouseEvent {x: number; y: number; button: number}
export const MouseContext = createContext<EventEmitter | undefined>(undefined);

export function terminalInput(input: NodeJS.ReadStream) {
  const events = new EventEmitter();
  events.setMaxListeners(100);
  const stream = new PassThrough() as PassThrough & {isTTY: boolean; setRawMode: (value: boolean) => void; ref: () => void; unref: () => void};
  // Keep incomplete UTF-8 bytes between chunks; decoding each chunk on its own
  // replaces a split multibyte character with U+FFFD before Ink receives it.
  stream.setEncoding('utf8');
  stream.isTTY = !!input.isTTY;
  stream.setRawMode = value => { input.setRawMode?.(value); };
  stream.ref = () => { input.ref?.(); };
  stream.unref = () => { input.unref?.(); };
  let partial = '';
  const decoder = new StringDecoder('utf8');
  const data = (chunk: Buffer | string) => {
    let value = partial + decoder.write(chunk); partial = '';
    value = value.replace(/\x1b\[<(\d+);(\d+);(\d+)([Mm])/g, (_match, button, x, y, action) => {
      if (action === 'M') events.emit('mouse', {button: Number(button), x: Number(x) - 1, y: Number(y) - 1});
      return '';
    });
    const incomplete = value.match(/\x1b\[<[\d;]*$/);
    if (incomplete) { partial = incomplete[0]; value = value.slice(0, -partial.length); }
    if (value) stream.write(value);
  };
  input.on('data', data);
  return {stream, events, dispose: () => { input.off('data', data); partial += decoder.end(); stream.end(partial || undefined); }};
}

export function HitBox({onClick, active = true, children, ...props}: BoxProps & {onClick: () => void; active?: boolean; children?: React.ReactNode}) {
  const ref = useRef<DOMElement>(null), events = useContext(MouseContext);
  useEffect(() => {
    const click = (event: MouseEvent) => {
      if (!active || event.button !== 0 || !ref.current) return;
      const {x, y, width, height} = measureElement(ref.current);
      if (event.x >= x && event.x < x + width && event.y >= y && event.y < y + height) onClick();
    };
    events?.on('mouse', click);
    return () => { events?.off('mouse', click); };
  }, [events, active, onClick]);
  return <Box ref={ref} {...props}>{children}</Box>;
}
