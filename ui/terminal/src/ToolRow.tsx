import {useEffect, useState} from 'react';
import {Box, Text} from 'ink';
import stringWidth from 'string-width';
import {clean, fit} from './editor.js';
import {formatElapsed, LatticeIcon} from './LatticeLoader.js';

export interface ToolActivity {
  name: string; args: Record<string, unknown>; status: string; output: string;
  startedAt?: number; finishedAt?: number; error?: string; exitCode?: number; diff?: string;
}
export interface ToolPresentation {activity: ToolActivity; indent?: number; expanded?: boolean}

export function toolTarget(args: Record<string, unknown>) {
  return clean(String(args.command ?? args.path ?? args.pattern ?? args.query ??
    Object.values(args).find(value => typeof value === 'string') ?? '')).replace(/\s+/g, ' ').trim();
}

export function toolSummary(tool: ToolActivity) {
  const output = clean(tool.output).split('\n').filter(line => line.trim());
  if (tool.status === 'running') return output.at(-1)?.trim() ?? '';
  if (tool.status === 'cancelled') return 'Stopped before completion';
  if (tool.status === 'failed') return clean(tool.error || output.at(-1) || 'Tool failed').split('\n').find(line => line.trim()) ?? 'Tool failed';
  const parts: string[] = [];
  if (tool.diff) {
    const diff = clean(tool.diff).split('\n');
    const added = diff.filter(line => line.startsWith('+') && !line.startsWith('+++')).length;
    const removed = diff.filter(line => line.startsWith('-') && !line.startsWith('---')).length;
    if (added || removed) parts.push(`+${added} −${removed}`);
  }
  if (tool.exitCode !== undefined) parts.push(`exit ${tool.exitCode}`);
  if (output.length && !tool.diff) parts.push(`${output.length} ${output.length === 1 ? 'line' : 'lines'} of output`);
  return parts.join(' · ');
}

export default function ToolRow({tool: {activity: tool, indent = 0, expanded = false}, width, now, animate}: {
  tool: ToolPresentation; width: number; now: number; animate: boolean;
}) {
  const [settleTime, setSettleTime] = useState(Date.now);
  useEffect(() => {
    if (tool.status !== 'completed' || !tool.finishedAt || Date.now() - tool.finishedAt >= 650) return;
    const timer = setInterval(() => {
      setSettleTime(Date.now());
      if (Date.now() - tool.finishedAt! >= 650) clearInterval(timer);
    }, 40);
    return () => clearInterval(timer);
  }, [tool.status, tool.finishedAt]);
  const running = tool.status === 'running';
  const end = tool.finishedAt ?? now;
  const duration = tool.startedAt === undefined ? '' : formatElapsed(Math.max(0, end - tool.startedAt) / 1000);
  const status = running ? 'Running' : tool.status === 'completed' ? 'Done' : tool.status === 'cancelled' ? 'Stopped' : 'Failed';
  const meta = `${status}${duration && width >= 46 ? ` ${duration}` : ''}`;
  const inner = Math.max(1, width - indent);
  const label = fit(`${tool.name}${toolTarget(tool.args) ? ` ${toolTarget(tool.args)}` : ''}`, Math.max(1, inner - stringWidth(meta) - 7));
  const freshness = tool.status === 'completed' && tool.finishedAt ? Math.max(0, 1 - (Math.max(now, settleTime) - tool.finishedAt) / 650) : 0;
  const shade = Math.round(160 + 95 * freshness).toString(16).padStart(2, '0');
  const foreground = running || tool.status === 'failed' ? '#f3f3f3' : `#${shade.repeat(3)}`;
  return <Box width={width} height={1} paddingLeft={indent}>
    <Box width={2} flexShrink={0}>{running && animate ? <LatticeIcon elapsed={Math.max(0, now - (tool.startedAt ?? now)) / 1000}/>
      : <Text color={foreground}>{running ? '·' : tool.status === 'completed' ? '✓' : tool.status === 'cancelled' ? '■' : '×'} </Text>}</Box>
    <Text color={foreground} bold wrap="truncate"> {label.slice(0, tool.name.length)}<Text color={running ? '#a0a0a0' : foreground} bold={false}>{label.slice(tool.name.length)}</Text></Text>
    <Box flexGrow={1}/>
    <Text color={running || tool.status === 'failed' ? '#a0a0a0' : '#737373'} wrap="truncate"> {meta} </Text>
    <Text color="#737373">{expanded ? '⌄' : '›'}</Text>
  </Box>;
}
