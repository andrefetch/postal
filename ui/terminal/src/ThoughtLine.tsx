import {useEffect, useRef, useState} from 'react';
import {Box, Text} from 'ink';
import stringWidth from 'string-width';
import wrapAnsi from 'wrap-ansi';
import {formatElapsed, LatticeIcon} from './LatticeLoader.js';
import {HitBox} from './mouse.js';
import {fit} from './editor.js';

export interface ThoughtLineProps {
  working?: boolean; label?: string; doneLabel?: string; glyph?: 'lattice' | 'sparkle' | 'dot' | 'none';
  outcome?: 'done' | 'error';
  steps?: string[]; collapsible?: boolean; collapseOnSettle?: boolean; showTimer?: boolean;
  elapsed?: number; breathPeriod?: number; breathDepth?: number; shimmer?: boolean; shimmerDuration?: number;
  settleDuration?: number; onSettle?: (seconds: number) => void;
  width?: number; open?: boolean; headOnly?: boolean; paused?: boolean; finishedAt?: number;
}
export const thoughtGrey = (opacity: number) => {
  const shade = Math.round(8 + 237 * Math.max(0, Math.min(1, opacity))).toString(16).padStart(2, '0');
  return `#${shade.repeat(3)}`;
};
export function thoughtEase(progress: number, out = false) {
  if (progress <= 0 || progress >= 1) return Math.max(0, Math.min(1, progress));
  const curve = (t: number, a: number, b: number) => 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t ** 2 * b + t ** 3;
  const [x1, y1, x2, y2] = out ? [0.23, 1, 0.32, 1] : [0.77, 0, 0.175, 1];
  let low = 0, high = 1;
  for (let i = 0; i < 16; i++) {
    const middle = (low + high) / 2;
    if (curve(middle, x1!, x2!) < progress) low = middle; else high = middle;
  }
  return curve((low + high) / 2, y1!, y2!);
}
export function thoughtBreath(seconds: number, period = 1.6, depth = 0.45) {
  // Match the initial 200 ms lead, then the source's two eased keyframe segments.
  if (seconds < 0.2) return 1 - depth * thoughtEase(Math.max(0, seconds) / 0.2, true);
  const phase = ((seconds - 0.2) % Math.max(0.1, period)) / Math.max(0.1, period);
  const wave = phase < 0.5 ? thoughtEase(phase * 2) : 1 - thoughtEase((phase - 0.5) * 2);
  return 1 - depth + depth * wave;
}
export function thoughtShimmer(index: number, length: number, seconds: number, duration = 1.8) {
  // CSS: background-size 250%, position 125% -> -125%, stops 30/50/70%.
  const progress = (seconds % Math.max(0.1, duration)) / Math.max(0.1, duration);
  const center = length * (-0.625 + progress * 3.75);
  return thoughtGrey(0.5 + 0.5 * Math.max(0, 1 - Math.abs(index + 0.5 - center) / Math.max(0.5, length * 0.5)));
}

export const liveThoughtKey = (id: number) => `thought:${id}:live`;
export function thoughtRows(steps: string[], width: number) {
  return steps.flatMap((step, index) => wrapAnsi(step, Math.max(1, width - 5), {hard: true, trim: false}).split('\n')
    .map((text, row) => ({text, step: index, continuation: row > 0, key: `${index}:${row}`})));
}

export function ThoughtStep({text, done, elapsed, width = 80, opacity = 1, continuation = false}: {
  text: string; done: boolean; elapsed: number; width?: number; opacity?: number; continuation?: boolean;
}) {
  const [enteredAt] = useState(Date.now), [entryTime, setEntryTime] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => {
      setEntryTime(Date.now());
      if (Date.now() - enteredAt >= 200) clearInterval(timer);
    }, 40);
    return () => clearInterval(timer);
  }, [enteredAt]);
  const entry = thoughtEase((entryTime - enteredAt) / 200, true) * opacity;
  const phase = (elapsed % 1.6) / 1.6;
  const pulse = 0.55 + 0.45 * (phase < 0.5 ? thoughtEase(phase * 2) : 1 - thoughtEase((phase - 0.5) * 2));
  return <Text wrap="truncate">{'   '}<Text color={thoughtGrey((done ? 0.55 : pulse) * entry)}>{continuation ? ' ' : done ? '✓' : '•'}</Text>
    <Text color={thoughtGrey((done ? 0.55 : 1) * entry)}> {fit(text, width - 5)}</Text>
  </Text>;
}

export default function ThoughtLine({working = true, label = 'Thinking…', doneLabel = 'Thought for', glyph = 'lattice', outcome = 'done',
  steps = [], collapsible = true, collapseOnSettle = true, showTimer = true, elapsed,
  breathPeriod = 1.6, breathDepth = 0.45, shimmer = true, shimmerDuration = 1.8,
  settleDuration = 350, onSettle, width = 80, open: controlledOpen, headOnly = false, paused = false, finishedAt,
}: ThoughtLineProps) {
  const [clock, setClock] = useState(0), [open, setOpen] = useState(working || !collapseOnSettle), [settleTime, setSettleTime] = useState(Date.now);
  const previous = useRef(working), transitionWorking = useRef(working), transitionAt = useRef(finishedAt), lastWorkingElapsed = useRef(0);
  const lastElapsed = useRef(0), callback = useRef(onSettle);
  if (transitionWorking.current !== working) {
    transitionAt.current = working ? undefined : finishedAt ?? Date.now();
    transitionWorking.current = working;
  }
  callback.current = onSettle;
  const seconds = Math.max(0, elapsed ?? clock);
  lastElapsed.current = seconds;
  if (working) lastWorkingElapsed.current = seconds;
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
    const start = finishedAt ?? transitionAt.current;
    if (working || start === undefined || Date.now() - start >= settleDuration) return;
    const timer = setInterval(() => {
      setSettleTime(Date.now());
      if (Date.now() - start >= settleDuration) clearInterval(timer);
    }, 40);
    return () => clearInterval(timer);
  }, [working, finishedAt, settleDuration]);
  const shown = controlledOpen ?? open, hasTrace = steps.length > 0;
  const start = finishedAt ?? transitionAt.current;
  const rawSettle = working ? 0 : start === undefined ? 1 : Math.min(1, Math.max(0, settleTime - start) / Math.max(1, settleDuration));
  const settle = thoughtEase(rawSettle, true);
  const outgoing = !working && rawSettle < 1 && 1 - settle > settle * 0.75;
  const textLimit = Math.max(1, width - (glyph === 'none' ? 0 : 3) - (showTimer ? formatElapsed(seconds).length + 1 : 0) - (hasTrace ? 2 : 0));
  const workText = fit(label, textLimit), doneText = fit(doneLabel, textLimit);
  const text = working || outgoing ? workText : doneText;
  const labelWidth = Math.round(working ? stringWidth(workText) : stringWidth(workText) + (stringWidth(doneText) - stringWidth(workText)) * thoughtEase(rawSettle));
  const glyphOpacity = working ? thoughtBreath(seconds, breathPeriod, breathDepth)
    : thoughtBreath(lastWorkingElapsed.current, breathPeriod, breathDepth) * (1 - settle) + 0.55 * settle;
  const fold = working || !collapseOnSettle || controlledOpen === true ? 1 : 1 - settle;
  const traceShown = !headOnly && (shown || (!working && fold > 0 && transitionAt.current !== undefined));
  const head = <Box height={1} width={width} aria-label={`${working ? label : doneLabel}${showTimer ? ` ${formatElapsed(seconds)}` : ''}`}>
    {glyph === 'lattice' ? <Text><LatticeIcon elapsed={seconds} status={working ? 'working' : outcome}
      color={thoughtGrey(glyphOpacity)} doneColor={thoughtGrey(glyphOpacity)} errorColor={thoughtGrey(glyphOpacity)}/>{' '}</Text>
      : glyph !== 'none' && <Text color={thoughtGrey(glyphOpacity)}>{glyph === 'sparkle' ? '✧˖' : '• '} </Text>}
    <Box width={labelWidth} overflow="hidden"><Text wrap="truncate">{[...text].map((character, index) => <Text key={index} color={working && shimmer
      ? thoughtShimmer(index, text.length, seconds, shimmerDuration) : thoughtGrey(working ? thoughtBreath(seconds, breathPeriod, breathDepth)
        : outgoing ? 1 - settle : 0.75 * settle)}>{character}</Text>)}</Text></Box>
    {showTimer && <Text color={thoughtGrey(working ? 0.55 : 0.55 + settle * 0.2)}> {formatElapsed(seconds)}</Text>}
    {collapsible && hasTrace && <Text color={thoughtGrey(0.55)}> {shown ? '⌃' : '⌄'}</Text>}
  </Box>;
  if (headOnly) return head;
  const trace = thoughtRows(steps, width);
  return <Box flexDirection="column" width={width}>
    <HitBox onClick={() => setOpen(value => !value)} active={collapsible && hasTrace}>{head}</HitBox>
    {hasTrace && (traceShown || !collapsible) && trace.slice(0, Math.ceil(trace.length * fold)).map(row =>
      <ThoughtStep key={row.key} text={row.text} continuation={row.continuation} done={!working || row.step < steps.length - 1} elapsed={seconds} width={width} opacity={fold}/>)}
  </Box>;
}
