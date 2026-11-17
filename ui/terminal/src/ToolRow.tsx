import {useEffect, useState} from 'react';
import {Box, Text} from 'ink';
import stringWidth from 'string-width';
import {fit} from './editor.js';
import {formatElapsed, LatticeIcon} from './LatticeLoader.js';
import {middleTruncate, shortPath, toolSummary, toolTarget, TOOL_SETTLE_DURATION, type ToolPresentation} from './toolPresentation.js';
export {toolSummary, toolTarget} from './toolPresentation.js';
export type {ToolActivity, ToolPresentation} from './toolPresentation.js';

export default function ToolRow({tool: {activity: tool, indent = 0, expanded = false, compact = false, summary}, width, now, animate}: {
  tool: ToolPresentation; width: number; now: number; animate: boolean;
}) {
  const [settleTime, setSettleTime] = useState(Date.now);
  useEffect(() => {
    if (tool.status !== 'completed' || tool.finishedAt === undefined || Date.now() - tool.finishedAt >= TOOL_SETTLE_DURATION) return;
    const timer = setInterval(() => {
      setSettleTime(Date.now());
      if (Date.now() - tool.finishedAt! >= TOOL_SETTLE_DURATION) clearInterval(timer);
    }, 40);
    return () => clearInterval(timer);
  }, [tool.status, tool.finishedAt]);
  const running = tool.status === 'running', clock = Math.max(now, settleTime);
  const end = tool.finishedAt ?? now;
  const duration = tool.startedAt === undefined ? '—' : formatElapsed(Math.max(0, end - tool.startedAt) / 1000);
  const status = running ? 'Running' : tool.status === 'completed' ? 'Done' : tool.status === 'cancelled' ? 'Stopped' : 'Failed';
  const inner = Math.max(1, width - indent), showDuration = width >= 46;
  const labelWidth = Math.max(1, inner - (showDuration ? 21 : 13));
  const detail = compact ? summary ?? toolSummary(tool) : '';
  const showSummary = !!detail && labelWidth >= 35;
  const titleBudget = showSummary ? Math.max(14, Math.floor(labelWidth * 0.6)) : labelWidth;
  const name = fit(tool.name, titleBudget);
  const targetBudget = Math.max(0, titleBudget - stringWidth(name) - 1);
  const rawTarget = toolTarget(tool.args);
  const path = typeof tool.args.path === 'string' && rawTarget === tool.args.path;
  const target = rawTarget && targetBudget > 0 ? path ? shortPath(rawTarget, targetBudget) : middleTruncate(rawTarget, targetBudget) : '';
  const titleWidth = stringWidth(name + (target ? ` ${target}` : ''));
  const summaryText = showSummary ? fit(` · ${detail}`, labelWidth - titleWidth) : '';
  const directoryEnd = path ? Math.max(target.lastIndexOf('/'), target.lastIndexOf('\\')) + 1 : 0;
  const freshness = tool.status === 'completed' && tool.finishedAt !== undefined ? Math.max(0, 1 - (clock - tool.finishedAt) / TOOL_SETTLE_DURATION) : 0;
  const shade = Math.round(160 + 95 * freshness).toString(16).padStart(2, '0');
  const foreground = running || tool.status === 'failed' ? '#f3f3f3' : `#${shade.repeat(3)}`;
  const settling = tool.status === 'completed' && tool.finishedAt !== undefined && clock - tool.finishedAt < 180;
  return <Box width={width} height={1} paddingLeft={indent}>
    <Box width={2} flexShrink={0}>{(running && animate) || settling ? <LatticeIcon elapsed={Math.max(0, end - (tool.startedAt ?? end)) / 1000}
      status={settling ? 'done' : 'working'} doneColor={foreground}/>
      : <Text color={foreground}>{running ? '·' : tool.status === 'completed' ? '✓' : tool.status === 'cancelled' ? '■' : '×'} </Text>}</Box>
    <Text> </Text>
    <Box width={labelWidth} overflow="hidden" flexShrink={0}>
      <Text wrap="truncate"><Text color={foreground} bold>{name}</Text>
        {target && <Text color={path ? '#737373' : '#a0a0a0'}> {target.slice(0, directoryEnd)}<Text bold={path} color={path ? foreground : '#a0a0a0'}>{target.slice(directoryEnd)}</Text></Text>}
        {summaryText && <Text color="#737373">{summaryText}</Text>}
      </Text>
    </Box>
    <Text> </Text>
    <Box width={7} flexShrink={0}><Text color={running || tool.status === 'failed' ? '#a0a0a0' : '#737373'}>{status}</Text></Box>
    {showDuration && <><Text> </Text><Box width={7} justifyContent="flex-end" flexShrink={0}><Text color="#737373">{fit(duration, 7)}</Text></Box></>}
    <Text color="#737373"> {expanded ? '⌄' : '›'}</Text>
  </Box>;
}
