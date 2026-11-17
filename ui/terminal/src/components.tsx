import {Box, Text} from 'ink';
import {basename} from 'node:path';
import {Marked} from 'marked';
import {markedTerminal} from 'marked-terminal';
import wrapAnsi from 'wrap-ansi';
import {clean, cursorRow, fit, visualLines, type Draft} from './editor.js';
import type {Block, State} from './state.js';
import {HitBox} from './mouse.js';

export const colors = {background: '#080808', panel: '#242424', menu: '#2c2c2c', text: '#f3f3f3', muted: '#a0a0a0', dim: '#737373', accent: '#eeeeee', line: '#454545'};
const plain = (text: string) => text;
const markdown = new Marked(markedTerminal({reflowText: false, showSectionPrefix: false, tab: 2,
  heading: plain, firstHeading: plain, codespan: plain, link: plain, href: plain,
  tableOptions: {style: {head: [], border: []}},
}) as any, {renderer: {code: ({text}) => `${clean(text).split('\n').map(line => `  ${line}`).join('\n')}\n\n`}});
export type Focus = 'input' | 'add' | 'model' | 'effort' | 'send';
export const focusOrder: Focus[] = ['input', 'add', 'model', 'effort', 'send'];

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
  const modelWidth = Math.max(6, Math.min(narrow ? 14 : 28, inner - 24));
  const disabled = !state.ready || state.busy || sending;
  return <Box width={width} flexDirection="column" paddingX={2} paddingY={padding} borderStyle="round"
    borderColor={focus === 'input' && active ? colors.line : colors.panel} borderBackgroundColor={colors.background} backgroundColor={colors.panel} flexShrink={0}>
    {(files.length > 0 || web) && <Box height={1} marginBottom={0} gap={1}>
      {files.length > 0 && <HitBox onClick={removeFiles} active={active} backgroundColor={colors.line} paddingX={1}><Text color={colors.accent}>{fit(files.length === 1 ? basename(files[0]!) : `${files.length} files`, Math.max(6, inner - 16))} ×</Text></HitBox>}
      {web && <HitBox onClick={removeWeb} active={active} backgroundColor={colors.line} paddingX={1}><Text color={colors.accent}>Web ×</Text></HitBox>}
    </Box>}
    <HitBox onClick={() => action('input')} active={active}><Editor draft={draft} width={inner} rows={inputRows} focused={focus === 'input' && active}/></HitBox>
    <Box height={1} width={inner} alignItems="center">
      <Control label="+" width={3} selected={focus === 'add'} disabled={disabled} onClick={() => active && action('add')}/>
      <Box width={1}/>
      <Control label={`${fit(model, modelWidth - 2)} ▾`} selected={focus === 'model'} disabled={disabled} onClick={() => active && action('model')}/>
      {!narrow && <Text color={colors.line}> · </Text>}
      <Control label={`${fit(effort[0]!.toUpperCase() + effort.slice(1), narrow ? 4 : 7)} ▾`} selected={focus === 'effort'} disabled={disabled} onClick={() => active && action('effort')}/>
      <Box flexGrow={1}/>
      <Control label={state.busy ? '■' : '↑'} width={3} selected={focus === 'send'} strong
        disabled={!state.ready || sending || (!state.busy && !draft.text.trim())} onClick={() => active && action('send')}/>
    </Box>
  </Box>;
}

export interface ConversationLine {text: string; block?: number; color?: string; activity?: boolean}
export function conversationLines(blocks: Block[], width: number, expanded: Set<number>): ConversationLine[] {
  const lines: ConversationLine[] = [];
  const push = (text: string, color?: string, block?: number, activity = false) => {
    for (const line of wrapAnsi(text, Math.max(1, width - (activity ? 2 : 0)), {hard: true, trim: false}).split('\n')) lines.push({text: line, color, block, activity});
  };
  for (const block of blocks) {
    if (block.kind === 'tool' || block.kind === 'reasoning') {
      const open = expanded.has(block.id);
      const active = block.status === 'running';
      const status = block.kind === 'reasoning' || active ? '' : block.status === 'completed' ? '✓ ' : '× ';
      const summary = block.kind === 'reasoning' ? 'Thinking…' : `${status}${block.title}  ${Object.values(block.args ?? {}).find(value => typeof value === 'string') ?? ''}`;
      push(`${open ? '⌄' : '›'} ${fit(summary, width - (active ? 4 : 2))}`, colors.muted, block.id, active);
      if (open) {
        if (block.args) push(clean(JSON.stringify(block.args, null, 2)), colors.dim);
        push(clean(block.text), colors.muted);
      }
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
