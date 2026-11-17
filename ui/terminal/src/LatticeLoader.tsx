import {Box, Text} from 'ink';

export type LatticeStatus = 'working' | 'done' | 'error';
export interface LatticeLoaderProps {
  status?: LatticeStatus; label?: string; doneLabel?: string; errorLabel?: string;
  elapsed?: number; step?: number; idleOpacity?: number; showTimer?: boolean;
  color?: string; doneColor?: string; errorColor?: string;
}
const ARROW = [1, 2, 3, 0, 1, 2, 1, 2, 3];
const MARKS = {done: [2, 3, 5, 7], error: [0, 2, 4, 6, 8]};

function ease(progress: number) {
  if (progress <= 0 || progress >= 1) return Math.max(0, Math.min(1, progress));
  // CSS cubic-bezier(0.77, 0, 0.175, 1), applied between each keyframe.
  const curve = (t: number, a: number, b: number) => 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t ** 2 * b + t ** 3;
  let low = 0, high = 1;
  for (let i = 0; i < 14; i++) {
    const middle = (low + high) / 2;
    if (curve(middle, 0.77, 0.175) < progress) low = middle; else high = middle;
  }
  return curve((low + high) / 2, 0, 1);
}

export function latticeOpacity(cell: number, elapsed: number, step = 100, idle = 0.14) {
  const time = elapsed * 1000 - ARROW[cell]! * step;
  if (time < 0) return idle;
  const phase = (time % Math.round(7.2 * step)) / Math.round(7.2 * step);
  if (phase < 0.18) return idle + (1 - idle) * ease(phase / 0.18);
  if (phase <= 0.42) return 1;
  if (phase < 0.62) return 1 - (1 - idle) * ease((phase - 0.42) / 0.2);
  return idle;
}

export function formatElapsed(seconds: number) {
  const ds = Math.max(0, Math.floor(seconds * 10));
  return ds < 600 ? `${(ds / 10).toFixed(1)}s` : `${Math.floor(ds / 600)}m ${((ds % 600) / 10).toFixed(1)}s`;
}

function blend(color: string, opacity: number) {
  return `#${[1, 3, 5].map(offset => Math.round(8 + (parseInt(color.slice(offset, offset + 2), 16) - 8) * opacity).toString(16).padStart(2, '0')).join('')}`;
}

// Braille packs the nine round cells into two character columns and one row.
const DOTS = [[1, 8], [2, 16], [4, 32]];
export function latticeGlyphs(elapsed: number, status: LatticeStatus = 'working', step = 100, idle = 0.14) {
  return [0, 1].map(column => {
    let bits = 0, all = 0, opacity = idle;
    for (let y = 0; y < 3; y++) for (let x = column * 2; x < Math.min(3, column * 2 + 2); x++) {
      const index = y * 3 + x, bit = DOTS[y]![x % 2]!;
      const brightness = status === 'working' ? latticeOpacity(index, elapsed, step, idle) : MARKS[status].includes(index) ? 1 : idle;
      all |= bit;
      if (brightness >= 0.5) bits |= bit;
      opacity = Math.max(opacity, brightness);
    }
    return {character: String.fromCodePoint(0x2800 + (bits || all)), opacity};
  });
}

export function LatticeIcon({status = 'working', elapsed = 0, step = 100, idleOpacity = 0.14,
  color = '#f5f5f5', doneColor = '#22c55e', errorColor = '#ef4444',
}: LatticeLoaderProps) {
  const fill = status === 'working' ? color : status === 'done' ? doneColor : errorColor;
  return <Text>{latticeGlyphs(elapsed, status, step, idleOpacity).map((cell, index) =>
    <Text key={index} color={blend(fill, cell.opacity)}>{cell.character}</Text>)}</Text>;
}

export default function LatticeLoader({status = 'working', label = 'Thinking', doneLabel = 'Done in', errorLabel = 'Failed after',
  elapsed = 0, showTimer = true, color = '#f5f5f5', ...iconProps
}: LatticeLoaderProps) {
  const text = status === 'working' ? label : status === 'done' ? doneLabel : errorLabel;
  return <Box height={1} aria-role="progressbar" aria-label={`${text}${showTimer ? ` ${formatElapsed(elapsed)}` : ''}`}>
    <LatticeIcon {...iconProps} status={status} elapsed={elapsed} color={color}/>
    <Text wrap="truncate" color={color}> {text}{showTimer && <Text color="#a0a0a0"> {formatElapsed(elapsed)}</Text>}</Text>
  </Box>;
}
