import stringWidth from 'string-width';
import {clean} from './editor.js';

export const TOOL_COMPACT_DELAY = 1600;
export const TOOL_SETTLE_DURATION = 650;
export type DetailKey = number | string;
export interface ToolActivity {
  name: string; args: Record<string, unknown>; status: string; output: string;
  startedAt?: number; finishedAt?: number; error?: string; exitCode?: number; diff?: string;
  metadata?: Record<string, unknown>; truncated?: boolean;
}
export interface ToolPresentation {
  activity: ToolActivity; indent?: number; expanded?: boolean; compact?: boolean; summary?: string;
}
export interface ToolItem {key: DetailKey; activity: ToolActivity}
export interface ToolGroup {key: string; items: ToolItem[]; activity: ToolActivity}
export const closedGroupKey = (key: string) => `closed:${key}`;
export const agentToolKey = (agentId: string, callId: string) => `tool:${agentId}:${callId}`;

export function toolTarget(args: Record<string, unknown>) {
  return clean(String(args.command ?? args.path ?? args.pattern ?? args.query ??
    Object.values(args).find(value => typeof value === 'string') ?? '')).replace(/\s+/g, ' ').trim();
}

export function middleTruncate(value: string, width: number) {
  if (width <= 0) return '';
  if (stringWidth(value) <= width) return value;
  const letters = [...new Intl.Segmenter(undefined, {granularity: 'grapheme'}).segment(value)].map(part => part.segment);
  let left = '', right = '', takeLeft = true;
  while (letters.length) {
    const next = takeLeft ? letters[0]! : letters.at(-1)!;
    if (stringWidth(left + next + '…' + right) > width) break;
    if (takeLeft) left += letters.shift(); else right = letters.pop()! + right;
    takeLeft = !takeLeft;
  }
  return `${left}…${right}`;
}

export function shortPath(value: string, width: number) {
  if (stringWidth(value) <= width) return value;
  const parts = value.replaceAll('\\', '/').split('/').filter(Boolean), file = parts.at(-1) ?? value;
  const abbreviated = `${value.startsWith('/') ? '/' : ''}${parts[0]}/…/${file}`;
  if (parts.length > 2 && stringWidth(abbreviated) <= width) return abbreviated;
  if (parts.length > 1 && stringWidth(`…/${file}`) <= width) return `…/${file}`;
  return middleTruncate(file, width);
}

export function toolDiffPreview(diff: string, limit = 3) {
  const changed: string[] = [];
  let hunk = false;
  for (const line of clean(diff).split('\n')) {
    if (line.startsWith('diff --git ')) hunk = false;
    if (line.startsWith('@@')) { hunk = true; continue; }
    if (!hunk && /^(?:\+\+\+|---)\s/.test(line)) continue;
    if (/^[+-]/.test(line)) changed.push(line);
  }
  return {lines: changed.slice(0, limit), remaining: Math.max(0, changed.length - limit),
    added: changed.filter(line => line.startsWith('+')).length, removed: changed.filter(line => line.startsWith('-')).length};
}

export function toolError(tool: ToolActivity) {
  const lines = clean(tool.error || tool.output || 'Tool failed').split('\n').map(line => line.trim()).filter(Boolean);
  const primary = lines.findLast(line => /(?:\w*(?:Error|Exception):|permission denied|not found|fatal:)/i.test(line)) ?? lines[0] ?? 'Tool failed';
  return [primary, ...lines.filter(line => line !== primary)].slice(0, 2);
}

export function toolSummary(tool: ToolActivity) {
  const output = clean(tool.output).split('\n').filter(line => line.trim());
  if (tool.status === 'running') return output.at(-1)?.trim() ?? '';
  if (tool.status === 'cancelled') return 'Stopped before completion';
  if (tool.status === 'failed') return toolError(tool)[0]!;
  const meta = tool.metadata ?? {}, parts: string[] = [];
  const count = (key: string) => typeof meta[key] === 'number' && Number.isFinite(meta[key]) ? Math.max(0, Number(meta[key])) : undefined;
  const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : word === 'match' ? 'es' : 's'}`;
  if (tool.name === 'read') {
    const start = count('shown_start'), end = count('shown_end');
    const numbered = output.filter(line => /^\s*\d+\|/.test(line)).length;
    const lines = start !== undefined && end !== undefined ? Math.max(0, end - start + 1) : count('lines') ?? (numbered || output.length);
    parts.push(`Read ${plural(lines, 'line')}`);
  } else if (['grep', 'glob', 'search'].includes(tool.name) && count('matches') !== undefined) {
    parts.push(`Found ${plural(count('matches')!, tool.name === 'glob' ? 'file' : 'match')}`);
    if (count('files_searched') !== undefined) parts.push(`${plural(count('files_searched')!, 'file')} searched`);
  } else if (['write', 'edit', 'apply_patch'].includes(tool.name)) {
    if (tool.name === 'write' && count('lines') !== undefined) parts.push(`${meta.is_new_file ? 'Created' : 'Wrote'} ${plural(count('lines')!, 'line')}`);
    if (tool.name === 'edit' && count('replaced_count') !== undefined) parts.push(`Replaced ${plural(count('replaced_count')!, 'occurrence')}`);
    if (tool.name === 'apply_patch' && count('files') !== undefined) parts.push(`Updated ${plural(count('files')!, 'file')}`);
  } else if (tool.name === 'bash') {
    const passed = clean(tool.output).match(/\b(\d+)\s+(?:tests?\s+)?passed\b/i) ?? clean(tool.output).match(/(?:#|ℹ)\s*pass\s+(\d+)/i);
    const failed = clean(tool.output).match(/\b([1-9]\d*)\s+failed\b/i);
    if (passed && !failed) parts.push(`${plural(Number(passed[1]), 'test')} passed`);
  }
  if (tool.diff) {
    const {added, removed} = toolDiffPreview(tool.diff);
    if (added || removed) parts.push(`+${added} −${removed}`);
  }
  if (tool.exitCode !== undefined) parts.push(`exit ${tool.exitCode}`);
  if (!parts.length && output.length) parts.push(`${plural(output.length, 'line')} of output`);
  if (tool.truncated) parts.push('output truncated');
  return parts.join(' · ');
}

export function toolDetails(tool: ToolActivity) {
  return [tool.output, tool.error && !tool.output.includes(tool.error) ? tool.error : '',
    tool.diff && !tool.output.includes(tool.diff) ? tool.diff : ''].filter(Boolean).join('\n');
}

export const groupCategory = (name: string) => name === 'read' ? 'read' : ['grep', 'glob', 'search'].includes(name) ? 'search' : undefined;
export function groupTools(items: ToolItem[], scope = 'main'): ToolGroup[] {
  const groups: ToolGroup[] = [];
  for (let i = 0; i < items.length;) {
    const first = items[i]!, category = groupCategory(first.activity.name), members = [first];
    let next = i + 1;
    while (category && next < items.length && groupCategory(items[next]!.activity.name) === category) members.push(items[next++]!);
    const tools = members.map(item => item.activity), running = tools.some(tool => tool.status === 'running');
    const status = running ? 'running' : tools.some(tool => tool.status === 'failed') ? 'failed' : tools.some(tool => tool.status === 'cancelled') ? 'cancelled' : 'completed';
    const paths = new Set(tools.map(tool => tool.args.path).filter(path => typeof path === 'string'));
    const name = members.length === 1 ? first.activity.name : category === 'read'
      ? paths.size ? `Read ${paths.size} file${paths.size === 1 ? '' : 's'}${paths.size < members.length ? ` · ${members.length} calls` : ''}` : `${members.length} reads`
      : `${members.length} searches`;
    const starts = tools.flatMap(tool => tool.startedAt === undefined ? [] : [tool.startedAt]);
    const ends = tools.flatMap(tool => tool.finishedAt === undefined ? [] : [tool.finishedAt]);
    groups.push({key: `group:${scope}:${first.key}`, items: members, activity: {name, args: {}, status, output: '',
      startedAt: starts.length ? Math.min(...starts) : undefined, finishedAt: !running && ends.length === tools.length ? Math.max(...ends) : undefined}});
    i = next;
  }
  return groups;
}

export function groupExpanded(group: ToolGroup, expanded: ReadonlySet<DetailKey>, now: number) {
  if (expanded.has(group.key)) return true;
  if (expanded.has(closedGroupKey(group.key))) return false;
  return group.items.some(item => item.activity.status !== 'completed' || (item.activity.finishedAt !== undefined && now - item.activity.finishedAt < TOOL_COMPACT_DELAY));
}

export function groupSummary(group: ToolGroup) {
  const counts = ['completed', 'running', 'failed', 'cancelled'].map(status => {
    const count = group.items.filter(item => item.activity.status === status).length;
    return count ? `${count} ${status === 'completed' ? 'done' : status === 'cancelled' ? 'stopped' : status}` : '';
  });
  return counts.filter(Boolean).join(' · ');
}
