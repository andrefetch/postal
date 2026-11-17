import {useEffect, useRef, useState} from 'react';
import {Box, Text} from 'ink';
import {formatElapsed} from './LatticeLoader.js';
import {HitBox} from './mouse.js';
import {fit} from './editor.js';

export interface ThoughtLineProps {
  working?: boolean; label?: string; doneLabel?: string; glyph?: 'sparkle' | 'dot' | 'none';
  steps?: string[]; collapsible?: boolean; collapseOnSettle?: boolean; showTimer?: boolean;
  elapsed?: number; breathPeriod?: number; breathDepth?: number; shimmer?: boolean; shimmerDuration?: number;
  settleDuration?: number; onSettle?: (seconds: number) => void;
  width?: number; open?: boolean; headOnly?: boolean; paused?: boolean; finishedAt?: number;
}
const grey = (opacity: number) => {
  const shade = Math.round(8 + 237 * Math.max(0, Math.min(1, opacity))).toString(16).padStart(2, '0');
  return `#${shade.repeat(3)}`;
};
export function thoughtBreath(seconds: number, period = 1.6, depth = 0.45) {
  return 1 - depth + depth * (1 - Math.cos(seconds * Math.PI * 2 / period)) / 2;
}
export function thoughtShimmer(index: number, length: number, seconds: number, duration = 1.8) {
  const center = ((seconds % duration) / duration) * (length + 6) - 3;
  return grey(0.5 + 0.5 * Math.max(0, 1 - Math.abs(index - center) / 3));
}

export default function ThoughtLine({working = true, label = 'Thinking…', doneLabel = 'Thought for', glyph = 'sparkle',
  steps = [], collapsible = true, collapseOnSettle = true, showTimer = true, elapsed,
  breathPeriod = 1.6, breathDepth = 0.45, shimmer = true, shimmerDuration = 1.8,
  settleDuration = 350, onSettle, width = 80, open: controlledOpen, headOnly = false, paused = false, finishedAt,
}: ThoughtLineProps) {
  const [clock, setClock] = useState(0), [open, setOpen] = useState(working || !collapseOnSettle), [settleTime, setSettleTime] = useState(Date.now);
  const previous = useRef(working), lastElapsed = useRef(0), callback = useRef(onSettle);
  callback.current = onSettle;
  const seconds = Math.max(0, elapsed ?? clock);
  lastElapsed.current = seconds;
  useEffect(() => {
    if (!working || elapsed !== undefined || paused) return;
    const start = performance.now(), base = lastElapsed.current;
    const timer = setInterval(() => setClock(base + (performance.now() - start) / 1000), 40);
    return () => clearInterval(timer);
  }, [working, elapsed, paused]);
  useEffect(() => {
    if (working) setOpen(true);
    else if (collapseOnSettle) setOpen(false);
    if (previous.current && !working) callback.current?.(lastElapsed.current);
    previous.current = working;
  }, [working, collapseOnSettle]);
  useEffect(() => {
    if (working || !finishedAt || Date.now() - finishedAt >= settleDuration) return;
    const timer = setInterval(() => {
      setSettleTime(Date.now());
      if (Date.now() - finishedAt >= settleDuration) clearInterval(timer);
    }, 40);
    return () => clearInterval(timer);
  }, [working, finishedAt, settleDuration]);
  const shown = controlledOpen ?? open, hasTrace = steps.length > 0;
  const settle = working ? 0 : finishedAt ? Math.min(1, Math.max(0, settleTime - finishedAt) / Math.max(1, settleDuration)) : 1;
  const text = fit(working ? label : doneLabel, Math.max(1, width - (glyph === 'none' ? 0 : 2) - (showTimer ? formatElapsed(seconds).length + 1 : 0) - (hasTrace ? 2 : 0)));
  const head = <Box height={1} width={width} aria-label={`${working ? label : doneLabel}${showTimer ? ` ${formatElapsed(seconds)}` : ''}`}>
    {glyph !== 'none' && <Text color={grey(working ? thoughtBreath(seconds, breathPeriod, breathDepth) : 1 - settle * 0.45)}>{glyph === 'sparkle' ? '✦' : '•'} </Text>}
    <Text wrap="truncate">{[...text].map((character, index) => <Text key={index} color={working && shimmer
      ? thoughtShimmer(index, text.length, seconds, shimmerDuration) : grey(working ? thoughtBreath(seconds, breathPeriod, breathDepth) : 1 - settle * 0.25)}>{character}</Text>)}</Text>
    {showTimer && <Text color={grey(working ? 0.55 : 0.75)}> {formatElapsed(seconds)}</Text>}
    {collapsible && hasTrace && <Text color={grey(0.55)}> {shown ? '⌃' : '⌄'}</Text>}
  </Box>;
  if (headOnly) return head;
  return <Box flexDirection="column" width={width}>
    <HitBox onClick={() => setOpen(value => !value)} active={collapsible && hasTrace}>{head}</HitBox>
    {hasTrace && (shown || !collapsible) && steps.map((step, index) => <Text key={index} color={grey(!working || index < steps.length - 1 ? 0.55 : 1)}>
      {`  ${!working || index < steps.length - 1 ? '✓' : '•'} ${fit(step, width - 4)}`}
    </Text>)}
  </Box>;
}
