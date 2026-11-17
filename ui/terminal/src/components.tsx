import {Box, Text} from 'ink';
import {basename} from 'node:path';
import {Marked} from 'marked';
import {markedTerminal} from 'marked-terminal';
import wrapAnsi from 'wrap-ansi';
import {clean, cursorRow, fit, visualLines, type Draft} from './editor.js';
import type {Block, State} from './state.js';
import {HitBox} from './mouse.js';
import {agentFinished} from './agents.js';
import type {LatticeStatus} from './LatticeLoader.js';
import {agentToolKey, groupExpanded, groupSummary, groupTools, toolDetails, toolDiffPreview, toolError, toolSummary, toolTarget, TOOL_COMPACT_DELAY, type DetailKey, type ToolActivity, type ToolGroup, type ToolItem, type ToolPresentation} from './toolPresentation.js';
import {mainTool} from './toolNavigation.js';
import {liveThoughtKey, thoughtEase, thoughtRows} from './ThoughtLine.js';

export const colors = {background: '#080808', panel: '#242424', menu: '#2c2c2c', text: '#f3f3f3', muted: '#a0a0a0', dim: '#737373', accent: '#eeeeee', line: '#454545'};
const plain = (text: string) => text;
const markdown = new Marked(markedTerminal({reflowText: false, showSectionPrefix: false, tab: 2,
  heading: plain, firstHeading: plain, codespan: plain, link: plain, href: plain,
  tableOptions: {style: {head: [], border: []}},
}) as any, {renderer: {code: ({text}) => `${clean(text).split('\n').map(line => `  ${line}`).join('\n')}\n\n`}});
export type Focus = 'input' | 'model' | 'effort' | 'approval';
export const focusOrder: Focus[] = ['input', 'model', 'effort', 'approval'];

export function Editor({draft, width, rows, focused, placeholder = 'Ask anything…'}: {
  draft: Draft; width: number; rows: number; focused: boolean; placeholder?: string;
}) {
  const lines = visualLines(draft.text, width), current = cursorRow(lines, draft.cursor);
  const start = Math.max(0, current - rows + 1);
  return <Box flexDirection="column" height={rows} width={width} overflow="hidden" aria-role="textbox" aria-state={{multiline: true}}>
    {Array.from({length: rows}, (_, index) => {
      const line = lines[start + index];
      if (!line) return <Text key={index}> </Text>;
      if (!draft.text) return <Text key={index} color={colors.muted}>{focused ? <Text backgroundColor={colors.accent} color={colors.panel}>{placeholder[0]}</Text> : placeholder[0]}{placeholder.slice(1)}</Text>;
      const local = draft.cursor - line.start;
      const atCursor = focused && start + index === current;
      const after = line.text.slice(local), character = [...new Intl.Segmenter(undefined, {granularity: 'grapheme'}).segment(after)][0]?.segment ?? ' ';
      return <Text key={index} color={colors.text} wrap="truncate">{atCursor ? <>{line.text.slice(0, local)}<Text backgroundColor={colors.accent} color={colors.panel}>{character}</Text>{after.slice(character.length)}</> : line.text}</Text>;
    })}
  </Box>;
}

function Control({label, selected, disabled = false, strong = false, onClick, width}: {
  label: string; selected: boolean; disabled?: boolean; strong?: boolean; onClick: () => void; width?: number;
}) {
  return <HitBox onClick={onClick} active={!disabled} paddingX={1} width={width} height={1} flexShrink={0}
    backgroundColor={strong && !disabled ? colors.accent : selected ? colors.line : colors.panel} aria-role="button" aria-state={{disabled, selected}}>
    <Text color={disabled ? colors.dim : strong ? colors.background : selected ? colors.text : colors.muted} bold={strong} wrap="truncate">{label}</Text>
  </HitBox>;
}

export interface PromptProps {
  state: State; draft: Draft; width: number; inputRows: number; padding: number; focus: Focus;
  files: string[]; web: boolean; sending: boolean; active?: boolean;
  action: (focus: Focus) => void; removeFiles: () => void; removeWeb: () => void;
}
export function PromptBar({state, draft, width, inputRows, padding, focus, files, web, sending, action, removeFiles, removeWeb, active = true}: PromptProps) {
  const inner = width - 6, narrow = width < 55;
  const effort = !state.settings.reasoning.enabled ? 'Off' : state.settings.reasoning.max_tokens ? 'Custom' : state.settings.reasoning.effort ?? 'Auto';
  const model = state.settings.model.split('/').at(-1) || 'Choose model';
  const mode = state.settings.approval || 'ask';
  const approval = {ask: 'Ask', 'on fail': 'On fail', auto: 'Auto', 'auto-edit': 'Auto-edit', 'read-only': 'Read-only', yolo: 'Yolo'}[mode] ?? 'Ask';
  const modelWidth = Math.max(6, Math.min(narrow ? 14 : 28, inner - 32));
  const disabled = !state.ready || state.busy || sending;
  return <Box width={width} flexDirection="column" paddingX={2} paddingY={padding} borderStyle="round"
    borderColor={focus === 'input' && active ? colors.line : colors.panel} borderBackgroundColor={colors.background} backgroundColor={colors.panel} flexShrink={0}>
    {(files.length > 0 || web) && <Box height={1} marginBottom={0} gap={1}>
      {files.length > 0 && <HitBox onClick={removeFiles} active={active} backgroundColor={colors.line} paddingX={1}><Text color={colors.accent}>{fit(files.length === 1 ? basename(files[0]!) : `${files.length} files`, Math.max(6, inner - 16))} ×</Text></HitBox>}
      {web && <HitBox onClick={removeWeb} active={active} backgroundColor={colors.line} paddingX={1}><Text color={colors.accent}>Web ×</Text></HitBox>}
    </Box>}
    <HitBox onClick={() => action('input')} active={active}><Editor draft={draft} width={inner} rows={inputRows} focused={focus === 'input' && active}/></HitBox>
    <Box height={1} width={inner} alignItems="center">
      <Control label={`${fit(model, modelWidth - 2)} ▾`} selected={focus === 'model'} disabled={disabled} onClick={() => active && action('model')}/>
      {!narrow && <Text color={colors.line}> · </Text>}
      <Control label={`${fit(effort[0]!.toUpperCase() + effort.slice(1), narrow ? 4 : 7)} ▾`} selected={focus === 'effort'} disabled={disabled} onClick={() => active && action('effort')}/>
      {!narrow && <Text color={colors.line}> · </Text>}
      <Control label={`${fit(approval, narrow ? 8 : 10)} ▾`} selected={focus === 'approval'} disabled={disabled} onClick={() => active && action('approval')}/>
      <Box flexGrow={1}/>
    </Box>
  </Box>;
}

export interface ConversationLine {key: string; text: string; block?: number; detailKey?: DetailKey; group?: ToolGroup; color?: string; activity?: boolean;
  thought?: {status: LatticeStatus; startedAt: number; finishedAt?: number; steps: string[]; open: boolean; doneLabel?: string};
  thoughtStep?: {text: string; done: boolean; continuation: boolean; startedAt: number; finishedAt?: number};
  tool?: ToolPresentation;
}
export function conversationLines(blocks: Block[], width: number, expanded: ReadonlySet<DetailKey>, activity?: Pick<State, 'busy' | 'status' | 'agents' | 'turnStartedAt'> & {now?: number}): ConversationLine[] {
  const lines: ConversationLine[] = [];
  let scope = 'activity', paragraph = 0;
  const push = (text: string, color?: string, block?: number, activity = false, key = `${scope}:paragraph:${paragraph++}`) => {
    for (const [row, line] of wrapAnsi(text, Math.max(1, width - (activity ? 3 : 0)), {hard: true, trim: false}).split('\n').entries()) {
      lines.push({key: `${key}:${row}`, text: line, color, block, activity});
    }
  };
  const thinking = (status: LatticeStatus, startedAt: number, finishedAt?: number, block?: number, steps: string[] = [], open = false, doneLabel?: string) => {
    const hidden = block !== undefined && expanded.has(-block - 1);
    const collapse = status !== 'working' && !open && finishedAt !== undefined && block !== undefined && !hidden
      ? 1 - thoughtEase(((activity?.now ?? Date.now()) - finishedAt) / 350, true) : 0;
    lines.push({key: `${scope}:head`, text: status === 'working' ? 'Thinking…' : doneLabel ?? 'Thought for', block, activity: status === 'working',
      thought: {status, startedAt, finishedAt, steps, open, doneLabel}});
    if (open || (status === 'working' && !hidden) || collapse > 0) {
      const rows = thoughtRows(steps, width);
      // Keep a short, advancing preview until the user explicitly opens the trace.
      const wasOpen = block !== undefined && expanded.has(liveThoughtKey(block));
      const visible = open || (collapse > 0 && wasOpen) ? rows : rows.slice(-4);
      const folding = open ? visible : visible.slice(0, Math.ceil(visible.length * collapse));
      for (const row of status === 'working' ? visible : folding) {
        const done = status !== 'working' || row.step < steps.length - 1;
        lines.push({key: `${scope}:step:${row.key}`, text: `   ${row.continuation ? ' ' : done ? '✓' : '•'} ${row.text}`, block,
          thoughtStep: {text: row.text, continuation: row.continuation, done, startedAt, finishedAt}});
      }
    }
  };
  const now = activity?.now ?? Date.now();
  const pushTool = (item: ToolActivity, key: DetailKey, open: boolean, indent = 0) => {
    const compact = !open && item.status === 'completed' && item.finishedAt !== undefined && now - item.finishedAt >= TOOL_COMPACT_DELAY;
    const block = typeof key === 'number' ? key : undefined;
    const lineKey = `tool:${JSON.stringify(key)}`;
    lines.push({key: `${lineKey}:head`, text: `${item.name} ${toolTarget(item.args)}`, block, detailKey: key, activity: item.status === 'running',
      tool: {activity: item, expanded: open, indent, compact}});
    const padding = ' '.repeat(indent), detailWidth = Math.max(1, width - indent - 4);
    let detailIndex = 0;
    const detail = (text: string, color = colors.dim, full = false) => {
      const detailKey = `${lineKey}:${open ? 'full' : 'preview'}:${detailIndex++}`;
      const content = full ? wrapAnsi(clean(text), detailWidth, {hard: true, trim: false}).split('\n') : [fit(text, detailWidth)];
      for (const [row, line] of content.entries()) lines.push({key: `${detailKey}:${row}`, text: `${padding}  │ ${line}`, color, detailKey: key, block});
    };
    if (open) {
      if (item.status === 'completed' && toolSummary(item)) detail(toolSummary(item), colors.muted);
      for (const [name, value] of Object.entries(item.args)) detail(`${name}  ${clean(typeof value === 'string' ? value : JSON.stringify(value) ?? String(value))}`, colors.dim, true);
      for (const line of clean(toolDetails(item)).split('\n')) detail(line, item.status === 'failed' ? colors.text : colors.muted, true);
    } else if (item.status === 'running') {
      const preview = clean(item.output).replaceAll('\r', '').split('\n').filter(line => line.trim()).slice(-2);
      detail(preview[0] ?? 'Waiting for output…');
      if (preview[1]) detail(preview[1]);
    } else if (item.status === 'failed') {
      const error = toolError(item);
      const preview = wrapAnsi(error.slice(0, 2).join(' '), detailWidth, {hard: true}).split('\n').slice(0, 2);
      for (const line of preview) detail(line, colors.text);
    } else if (!compact) {
      const summary = toolSummary(item);
      if (summary) lines.push({key: `${lineKey}:summary`, text: `${padding}  └ ${fit(summary, detailWidth)}`, color: colors.dim, detailKey: key, block});
      if (item.diff) {
        const preview = toolDiffPreview(item.diff);
        for (const line of preview.lines) detail(line, line.startsWith('+') ? colors.text : colors.muted);
        if (preview.remaining) detail(`… ${preview.remaining} more changed ${preview.remaining === 1 ? 'line' : 'lines'}`);
      }
    }
  };
  const pushTools = (items: ToolItem[], scope: string, indent = 0) => {
    for (const group of groupTools(items, scope)) {
      if (group.items.length === 1) {
        const item = group.items[0]!;
        pushTool(item.activity, item.key, expanded.has(item.key), indent);
        continue;
      }
      const open = groupExpanded(group, expanded, now);
      lines.push({key: group.key, text: group.activity.name, detailKey: group.key, group, activity: group.activity.status === 'running',
        tool: {activity: group.activity, expanded: open, indent, compact: !open, summary: groupSummary(group)}});
      for (const item of group.items) if (open || item.activity.status === 'failed') {
        pushTool(item.activity, item.key, expanded.has(item.key), indent + 2);
      }
    }
  };
  for (let index = 0; index < blocks.length; index++) {
    const block = blocks[index]!;
    scope = `block:${block.id}`; paragraph = 0;
    if (block.kind === 'agent') {
      const agent = activity?.agents[block.agentId!];
      if (!agent) continue;
      const open = expanded.has(block.id), finished = agentFinished(agent.status);
      const prefix = '  '.repeat(Math.max(0, Math.min(3, agent.depth - 1)));
      if (lines.length) push('');
      push(`${prefix}${open ? '⌄' : '›'} ${clean(agent.name)} · ${agent.status.replaceAll('_', ' ')} · ${agent.tools.length} tool${agent.tools.length === 1 ? '' : 's'}${agent.usage?.total_tokens ? ` · ${agent.usage.total_tokens.toLocaleString()} tokens` : ''}`, colors.text, block.id, false, `${scope}:head`);
      if (agent.goal) push(`${prefix}  ${fit(clean(agent.goal).replaceAll('\n', ' '), width - prefix.length - 2)}`, colors.dim, undefined, false, `${scope}:goal`);
      pushTools(agent.tools.map(tool => ({key: agentToolKey(agent.agent_id, tool.callId), activity: tool})), agent.agent_id, prefix.length + 2);
      if (!finished && !agent.tools.some(tool => tool.status === 'running')) push(`${prefix}  ${agent.phase}`, colors.muted, block.id, agent.status === 'running', `${scope}:phase`);
      if (agent.error) push(`${prefix}  ${clean(agent.error)}`, colors.text, undefined, false, `${scope}:error`);
      if (open && agent.result) push(clean(agent.result), colors.muted, undefined, false, `${scope}:result`);
    } else if (block.kind === 'tool') {
      const run = [block];
      while (blocks[index + 1]?.kind === 'tool') run.push(blocks[++index]!);
      pushTools(run.map(item => ({key: item.id, activity: mainTool(item)})), 'main');
    } else if (block.kind === 'reasoning') {
      const active = block.status === 'running';
      const open = expanded.has(active ? liveThoughtKey(block.id) : block.id);
      thinking(active ? 'working' : block.status === 'completed' ? 'done' : 'error',
        block.startedAt ?? 0, block.finishedAt, block.id, clean(block.text).split(/\n+/).map(line => line.trim()).filter(Boolean), open,
        block.status === 'cancelled' ? 'Stopped after' : block.status === 'failed' ? 'Failed after' : undefined);
    } else {
      if (lines.length) push('');
      if (block.kind !== 'notice') push(block.kind === 'user' ? 'You' : 'Postal', block.kind === 'user' ? colors.muted : colors.accent);
      if (block.files?.length || block.web) push([...(block.files ?? []).map(path => basename(path)), ...(block.web ? ['Web search'] : [])].join(' · '), colors.dim);
      const text = clean(block.text);
      if (block.kind === 'assistant') {
        try { push((markdown.parse(text) as string).trimEnd(), colors.text); }
        catch { push(text, colors.text); }
      } else push(text, block.kind === 'notice' ? colors.muted : colors.text);
      push('');
    }
  }
  scope = `activity:${activity?.turnStartedAt ?? 0}`; paragraph = 0;
  if (activity?.busy && !blocks.some(block => (block.kind === 'reasoning' || block.kind === 'tool') && block.status === 'running')) {
    if (activity.status === 'Responding') push('› Responding…', colors.muted, undefined, true);
    else thinking('working', activity.turnStartedAt ?? 0);
  }
  return lines;
}

export interface Choice {key: string; label: string; detail?: string; disabled?: boolean}
export function Menu({title, choices, selected, input, width, height, error, onChoose, onClose}: {
  title: string; choices: Choice[]; selected: number; input?: Draft; width: number; height: number;
  error?: string; onChoose: (choice: Choice) => void; onClose: () => void;
}) {
  const count = Math.max(1, height - (input ? 8 : 6)), start = Math.max(0, selected - count + 1);
  return <Box flexDirection="column" width={width} maxHeight={height} backgroundColor={colors.menu} borderStyle="round" borderColor={colors.line} paddingX={2} paddingY={height < 16 ? 0 : 1}>
    <Box height={1} justifyContent="space-between"><Text bold color={colors.text}>{title}</Text><HitBox onClick={onClose}><Text color={colors.dim}>esc</Text></HitBox></Box>
    {input && <Box marginTop={1} marginBottom={1}><Editor draft={input} width={width - 6} rows={1} focused placeholder="Type to search…"/></Box>}
    {choices.slice(start, start + count).map((choice, offset) => <HitBox key={choice.key} onClick={() => onChoose(choice)} active={!choice.disabled}
      height={1} backgroundColor={start + offset === selected ? colors.line : colors.menu}>
      <Text color={choice.disabled ? colors.dim : start + offset === selected ? colors.accent : colors.text} wrap="truncate">
        {start + offset === selected ? '› ' : '  '}{fit(choice.label, Math.max(4, width - 10))}{width >= 60 && choice.detail ? <Text color={colors.muted}>  {choice.detail}</Text> : ''}
      </Text>
    </HitBox>)}
    {error && <Text color={colors.text} wrap="truncate">{clean(error)}</Text>}
    <Box marginTop={1}><Text color={colors.dim}>{choices.length ? '↑ ↓ choose   enter select' : 'Enter confirm'}{input ? '   esc close' : ''}</Text></Box>
  </Box>;
}
