import {useEffect, useMemo, useRef, useState} from 'react';
import {Box, Text} from 'ink';

export interface SnowRect {x: number; y: number; width: number; height: number}
export interface PixelSnowProps {
  columns: number; rows: number; exclusions?: SnowRect[]; paused?: boolean;
  color?: string; variant?: 'snowflake' | 'square' | 'round'; density?: number;
  speed?: number; wind?: number; sway?: number; depth?: number;
  brightness?: number; twinkle?: number; opacity?: number; intro?: boolean;
}
interface Flake {x: number; y: number; level: number; phase: number; rate: number; drift: number; sparkle: number; reveal: number}
export interface SnowCell {x: number; y: number; character: string; color: string}
const WEIGHTS = [0.46, 0.27, 0.15, 0.08, 0.04];
const FALL = [16, 24, 34, 48, 66];
const LIGHT = [0.42, 0.58, 0.76, 0.92, 1];
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));
const wrap = (value: number, limit: number) => ((value % limit) + limit) % limit;

function createFlakes(count: number): Flake[] {
  let seed = 4271;
  const random = () => {
    seed = (seed + 0x6d2b79f5) >>> 0;
    let t = Math.imul(seed ^ (seed >>> 15), seed | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return Array.from({length: count}, () => {
    const choice = random();
    let cumulative = 0;
    const level = WEIGHTS.findIndex(weight => { cumulative += weight; return choice <= cumulative; });
    return {x: random(), y: random(), level: Math.max(0, level), phase: random() * Math.PI * 2,
      rate: 0.6 + random() * 0.9, drift: 0.7 + random() * 0.6, sparkle: random() * 100, reveal: random()};
  });
}

export function snowFrame({columns, rows, exclusions = [], color = '#ffffff', variant = 'snowflake', density = 0.5,
  speed = 1, wind = 0.25, sway = 0.5, depth = 0.6, brightness = 0.2, twinkle = 0.35, opacity = 1, intro = true,
}: PixelSnowProps, seconds: number): SnowCell[] {
  if (columns < 1 || rows < 1 || brightness <= 0 || opacity <= 0) return [];
  const flakes = createFlakes(Math.min(160, Math.round(columns * rows * clamp(density, 0, 1) / 32)));
  const cells = new Map<string, SnowCell>();
  const reveal = intro ? Math.min(1, seconds / 1.4) : 1;
  for (const flake of flakes) {
    const level = flake.level, parallax = 1 - clamp(depth, 0, 1) * (1 - (level + 1) / 5) * 0.75;
    const x = Math.floor(wrap(flake.x * columns + seconds * wind * 5.75 * parallax * flake.drift +
      Math.sin(seconds * flake.rate + flake.phase) * sway * (0.6 + level * 0.4), columns));
    const y = Math.floor(wrap(flake.y * rows + seconds * FALL[level]! / 20 * parallax * speed * flake.drift, rows));
    if (exclusions.some(rect => x >= rect.x && x < rect.x + rect.width && y >= rect.y && y < rect.y + rect.height)) continue;
    const visibility = reveal >= 1 ? 1 : clamp((reveal * 1.75 - y / rows - flake.reveal * 0.25) / 0.35, 0, 1);
    if (!visibility) continue;
    const spark = Math.max(0, Math.sin(seconds * 0.9 + flake.sparkle)) ** 60 * twinkle;
    const light = (1 - depth * (1 - LIGHT[level]!)) * (0.85 + spark * 0.6) * visibility ** 2;
    const alpha = (1 - Math.exp(-Math.max(0, light * brightness) * 1.6)) * clamp(opacity, 0, 1);
    const tint = `#${[1, 3, 5].map(offset => Math.round(8 + (parseInt(color.slice(offset, offset + 2), 16) - 8) * alpha).toString(16).padStart(2, '0')).join('')}`;
    const character = variant === 'square' ? '▪' : variant === 'round' ? '∙' : ['·', '∙', '✦', '❄', '❄'][level]!;
    cells.set(`${x},${y}`, {x, y, character, color: tint});
  }
  return [...cells.values()];
}

export default function PixelSnow({paused = false, ...props}: PixelSnowProps) {
  const [seconds, setSeconds] = useState(0), elapsed = useRef(0);
  useEffect(() => {
    if (paused) return;
    const start = performance.now(), base = elapsed.current;
    const timer = setInterval(() => {
      elapsed.current = base + (performance.now() - start) / 1000;
      setSeconds(elapsed.current);
    }, 100);
    return () => clearInterval(timer);
  }, [paused]);
  const cells = useMemo(() => snowFrame(props, seconds), [props.columns, props.rows, props.exclusions, props.color,
    props.variant, props.density, props.speed, props.wind, props.sway, props.depth, props.brightness, props.twinkle, props.opacity, props.intro, seconds]);
  return <Box position="absolute" top={0} left={0} width={props.columns} height={props.rows} overflow="hidden" aria-hidden>
    {cells.map(cell => <Box key={`${cell.x},${cell.y}`} position="absolute" left={cell.x} top={cell.y} height={1} width={1}>
      <Text color={cell.color}>{cell.character}</Text>
    </Box>)}
  </Box>;
}
