import {useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState} from 'react';
import {Box, Text, useApp, useInput, usePaste, useWindowSize} from 'ink';
import {basename} from 'node:path';
import wrapAnsi from 'wrap-ansi';
import type {Transport} from './protocol.js';
import {agentDetails} from './agents.js';
import {initialState, reduce, type State} from './state.js';
import {clean, edit, emptyDraft, fit, insert, visualLines, type Draft} from './editor.js';
import {colors, conversationLines, focusOrder, Menu, PromptBar, type Choice, type Focus, type PromptProps, type ConversationLine} from './components.js';
import {HitBox, MouseContext, type MouseEvent} from './mouse.js';
import {LoadingText, useActivityFrame} from './activity.js';
import ThoughtLine, {ThoughtStep} from './ThoughtLine.js';
import PixelSnow, {type SnowRect} from './PixelSnow.js';
import ToolRow from './ToolRow.js';
import {closedGroupKey, groupExpanded, TOOL_COMPACT_DELAY, type DetailKey} from './toolPresentation.js';
import {conversationToolGroups, expandTools} from './toolNavigation.js';

type MenuKind = 'context' | 'model' | 'effort' | 'file' | 'commands' | 'agents';
interface OpenMenu {kind: MenuKind; input: Draft; index: number; error?: string; scroll: number}
export function layout(columns: number, rows: number, home: boolean, draft: Draft, sources: boolean) {
  const width = Math.max(26, Math.min(home ? 70 : 96, columns - 4));
  const padding = rows >= 22 ? 1 : 0;
  const inputRows = Math.min(Math.max(1, rows - 18), 5, Math.max(rows >= 22 ? 2 : 1, visualLines(draft.text, width - 6).length));
  const promptHeight = 2 + padding * 2 + inputRows + 1 + Number(sources);
  const header = rows >= 18 ? 2 : 0, welcome = home ? 4 + Number(rows >= 22) : 0;
  return {width, padding, inputRows, promptHeight, header, welcome,
    top: Math.max(0, Math.floor((rows - promptHeight) / 2) - header - welcome),
    conversation: Math.max(1, rows - header - promptHeight - 2)};
}

export interface ViewProps extends Omit<PromptProps, 'width' | 'inputRows' | 'padding'> {
  columns: number; rows: number; lines: ConversationLine[]; scroll: number | null;
  toggle: (id: DetailKey) => void; toast: string; overlay?: React.ReactNode;
}
export function TerminalView(props: ViewProps) {
  const {state, columns, rows, draft, files, web, lines, scroll, toggle, toast, overlay} = props;
  const animate = state.busy && !state.approval;
  const frame = useActivityFrame(animate);
  const pausedAt = useRef<number | undefined>(undefined);
  if (animate) pausedAt.current = undefined;
  else pausedAt.current ??= Date.now();
  const home = state.blocks.length === 0;
  const dimensions = layout(columns, rows, home, draft, files.length > 0 || web);
  const maxScroll = Math.max(0, lines.length - dimensions.conversation);
  const offset = Math.min(maxScroll, scroll ?? maxScroll);
  const statusWidth = dimensions.width - (dimensions.width > 55 ? 28 : 0);
  const contentX = Math.floor((columns - dimensions.width) / 2);
  const promptY = dimensions.header + (home ? dimensions.top + dimensions.welcome : dimensions.conversation);
  const snowExclusions: SnowRect[] = [
    {x: 0, y: 0, width: columns, height: dimensions.header},
    {x: contentX - 1, y: promptY, width: dimensions.width + 2, height: dimensions.promptHeight + 2},
    home ? {x: Math.floor((columns - 22) / 2) - 1, y: dimensions.header + dimensions.top, width: 24, height: dimensions.welcome}
      : {x: contentX - 1, y: dimensions.header, width: dimensions.width + 2, height: dimensions.conversation},
  ];
  if (columns < 32 || rows < 10) return <Box width={columns} height={rows}><Text>Resize to at least 32 × 10. Ctrl+Q quits.</Text></Box>;
  return <Box width={columns} height={rows} flexDirection="column" alignItems="center" backgroundColor={colors.background} overflow="hidden">
    <PixelSnow columns={columns} rows={rows} exclusions={snowExclusions} paused={!!overlay}/>
    {dimensions.header > 0 && <Box width={columns - 4} height={2} justifyContent="space-between">
      <Box flexGrow={1}/>
      <Text color={colors.dim} wrap="truncate">{fit(state.settings.cwd, Math.max(10, columns - 20))}</Text>
    </Box>}
    {home ? <>
      <Box height={dimensions.top} flexShrink={0}/>
      <Box flexDirection="column" alignItems="center" height={dimensions.welcome} flexShrink={0}>
        {state.logo.map((line, index) => <Text key={index} color={colors.text}>{line}</Text>)}
      </Box>
    </> : <Box width={dimensions.width} height={dimensions.conversation} flexDirection="column" overflow="hidden" flexShrink={0}>
      {lines.slice(offset, offset + dimensions.conversation).map((line, index) => <HitBox key={offset + index}
        onClick={() => { const key = line.detailKey ?? line.block; if (key !== undefined) toggle(key); }} active={!overlay && (line.detailKey ?? line.block) !== undefined} height={1}>
        {line.tool ? <ToolRow tool={line.tool} width={dimensions.width} now={animate ? Date.now() : pausedAt.current!} animate={animate}/>
          : line.thoughtStep ? <ThoughtStep text={line.thoughtStep.text} done={line.thoughtStep.done} width={dimensions.width}
            elapsed={Math.max(0, ((line.thoughtStep.finishedAt ?? (animate ? Date.now() : pausedAt.current!)) - line.thoughtStep.startedAt) / 1000)}/>
          : line.thought ? <ThoughtLine working={line.thought.status === 'working'} label="Thinking…" doneLabel={line.thought.doneLabel ?? 'Thought for'}
            outcome={line.thought.status === 'error' ? 'error' : 'done'}
            steps={line.thought.steps} open={line.thought.open} headOnly width={dimensions.width} paused={!animate} finishedAt={line.thought.finishedAt}
            elapsed={Math.max(0, ((line.thought.finishedAt ?? (animate ? Date.now() : pausedAt.current!)) - line.thought.startedAt) / 1000)}/>
          : line.activity && animate ? <LoadingText text={line.text} frame={frame}/> : <Text color={line.color} wrap="truncate">{line.text || ' '}</Text>}
      </HitBox>)}
    </Box>}
    <PromptBar {...props} width={dimensions.width} inputRows={dimensions.inputRows} padding={dimensions.padding} active={!overlay}/>
    <Box width={dimensions.width} height={2} paddingTop={1} justifyContent="space-between" flexShrink={0}>
      <Box width={statusWidth} overflow="hidden">
        <Text color={colors.dim} wrap="truncate">{fit(toast || `${state.approval ? 'Awaiting approval' : state.busy ? 'esc stop' : state.status} · ${state.settings.approval}${state.tokens ? ` · ${state.tokens.toLocaleString()} tokens` : ''}`, statusWidth)}</Text>
      </Box>
      {dimensions.width > 55 && <Text color={colors.dim}>{scroll !== null && offset < maxScroll ? 'pgdn latest' : state.blocks.some(block => block.kind === 'tool' || block.kind === 'agent') ? 'ctrl+o details · alt+o group' : '/ commands    enter send'}</Text>}
    </Box>
    {overlay && <Box position="absolute" top={0} left={0} width={columns} height={rows} alignItems="center" justifyContent="center">{overlay}</Box>}
  </Box>;
}

export function PostalApp({backend, size}: {backend: Transport; size?: {columns: number; rows: number}}) {
  const window = useWindowSize(), {exit} = useApp(), mouse = useContext(MouseContext);
  const {columns, rows} = size ?? window;
  const [state, dispatch] = useReducer(reduce, initialState);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [focus, setFocus] = useState<Focus>('input');
  const [files, setFiles] = useState<string[]>([]), [web, setWeb] = useState(false);
  const [menu, setMenu] = useState<OpenMenu | undefined>();
  const [expanded, setExpanded] = useState(new Set<DetailKey>());
  const [scroll, setScroll] = useState<number | null>(null);
  const [approvalScroll, setApprovalScroll] = useState(0), [approvalChoice, setApprovalChoice] = useState(false);
  const [toast, setToast] = useState(''), [sending, setSending] = useState(false);
  const [history, setHistory] = useState<string[]>([]), [historyIndex, setHistoryIndex] = useState<number | null>(null);
  const savedDraft = useRef<Draft>(emptyDraft()), quitting = useRef(false);
  const home = state.blocks.length === 0;
  const dimensions = layout(columns, rows, home, draft, files.length > 0 || web);
  const settlingThoughts = state.blocks.some(block => block.kind === 'reasoning' && block.finishedAt !== undefined && Date.now() - block.finishedAt < 350);
  const recentTool = (tool: {finishedAt?: number}) => tool.finishedAt !== undefined && Date.now() - tool.finishedAt < TOOL_COMPACT_DELAY;
  const settlingTools = state.blocks.some(block => block.kind === 'tool' && recentTool(block)) || Object.values(state.agents).some(agent => agent.tools.some(recentTool));
  const presentationFrame = useActivityFrame(settlingThoughts || settlingTools);
  const lines = useMemo(() => conversationLines(state.blocks, dimensions.width, expanded, {...state, now: Date.now()}),
    [state.blocks, dimensions.width, expanded, state.agents, state.busy, state.status, presentationFrame]);
  const maxScroll = Math.max(0, lines.length - dimensions.conversation);
  const report = useCallback((error: unknown) => setToast(error instanceof Error ? error.message : String(error)), []);
  const request = useCallback((method: string, params: Record<string, unknown> = {}) => backend.request(method, params).catch(report), [backend, report]);
  const openMenu = useCallback((kind: MenuKind) => {
    const text = kind === 'model' ? state.settings.model : '';
    setMenu({kind, input: {text, cursor: text.length}, index: 0, scroll: 0});
  }, [state.settings.model]);
  const quit = useCallback(async () => {
    if (quitting.current) return;
    quitting.current = true;
    setToast('Closing session…');
    try { await backend.close(); } finally { exit(); }
  }, [backend, exit]);
  useEffect(() => backend.subscribe(message => {
    if (message.type === 'ready') setHistory(message.history);
    if (message.type === 'ready' || message.type === 'transcript') setExpanded(new Set());
    if (message.type === 'toast') setToast(message.text.split('\n')[0] ?? '');
    if (message.type === 'exit') { void quit(); return; }
    if (message.type === 'open_agents') setMenu({kind: 'agents', input: emptyDraft(), index: 0, scroll: 0});
    if (message.type === 'transcript' || message.type === 'turn_start') setScroll(null);
    if (message.type === 'approval') { setApprovalChoice(false); setApprovalScroll(0); }
    dispatch(message);
  }), [backend, quit]);
  useEffect(() => { void request('resize', {columns}); }, [request, columns]);
  useEffect(() => { if (toast) { const timer = setTimeout(() => setToast(''), 5000); return () => clearTimeout(timer); } }, [toast]);
  const moveScroll = useCallback((amount: number) => setScroll(current => {
    const next = Math.max(0, Math.min(maxScroll, (current ?? maxScroll) + amount));
    return next >= maxScroll ? null : next;
  }), [maxScroll]);
  useEffect(() => {
    const wheel = (event: MouseEvent) => {
      if (event.button !== 64 && event.button !== 65) return;
      const delta = event.button === 64 ? -3 : 3;
      if (state.approval) setApprovalScroll(current => Math.max(0, current + delta));
      else if (!menu) moveScroll(delta);
    };
    mouse?.on('mouse', wheel);
    return () => { mouse?.off('mouse', wheel); };
  }, [mouse, moveScroll, menu, state.approval]);
  const toggle = (id: DetailKey) => setExpanded(current => {
    const group = conversationToolGroups(state.blocks, state.agents).find(group => group.key === id);
    if (group) {
      const next = new Set(current);
      if (groupExpanded(group, current, Date.now())) { next.delete(group.key); next.add(closedGroupKey(group.key)); }
      else { next.add(group.key); next.delete(closedGroupKey(group.key)); }
      return next;
    }
    const block = state.blocks.find(block => block.id === id);
    const key = typeof id === 'number' && block?.kind === 'reasoning' && block.status === 'running' ? -id - 1 : id;
    const next = new Set(current); if (next.has(key)) next.delete(key); else next.add(key); return next;
  });
  const submit = async () => {
    if (state.busy) { await request('cancel'); return; }
    if (!state.ready || sending || !draft.text.trim()) return;
    const text = draft.text;
    setSending(true);
    try {
      await backend.request('submit', {text, files, web});
      setDraft(current => current.text === text ? emptyDraft() : current);
      setFiles([]); setWeb(false); setFocus('input'); setHistory(current => [...current, text]); setHistoryIndex(null);
    } catch (error) { report(error); }
    finally { setSending(false); }
  };
  const action = (target: Focus) => {
    setFocus(target);
    if (target === 'send') void submit();
    else if (target !== 'input' && state.ready && !state.busy && !sending) openMenu(target === 'add' ? 'context' : target);
  };
  const agents = Object.values(state.agents);
  const choices: Choice[] = useMemo(() => {
    if (!menu) return [];
    const query = menu.input.text.toLowerCase();
    switch (menu.kind) {
      case 'context': return [
        ...(state.capabilities.read ? [{key: 'file', label: 'Add a file', detail: 'Text and code from this workspace'}] : []),
        ...(state.capabilities.search ? [{key: 'web', label: web ? 'Remove web search' : 'Web search', detail: 'Use live sources for this prompt'}] : []),
        {key: 'commands', label: 'Commands', detail: 'Browse slash commands'},
      ];
      case 'effort': return ['auto', 'minimal', 'low', 'medium', 'high', 'none'].map(value => ({key: value,
        label: value === 'none' ? 'Off' : value[0]!.toUpperCase() + value.slice(1), detail: value === 'auto' ? 'Let the model decide' : ''}));
      case 'model': {
        const values = [...new Set([menu.input.text.trim(), ...state.recentModels.toReversed()])].filter(Boolean);
        return values.filter(value => value.toLowerCase().includes(query)).map(value => ({key: value, label: value,
          detail: value === state.settings.model ? 'Current' : state.recentModels.includes(value) ? 'Recent' : 'Use this model'}));
      }
      case 'commands': return state.commands.filter(command => command.name.startsWith(query.replace(/^\//, ''))).map(command => ({key: command.name, label: `/${command.name}`, detail: command.description}));
      case 'agents': return agents.map(agent => ({key: agent.agent_id, label: `${'  '.repeat(agent.depth)}${agent.name} · ${agent.status}`}));
      default: return [];
    }
  }, [menu, state.capabilities, state.commands, state.recentModels, state.settings.model, state.agents, web]);
  const selected = Math.max(0, Math.min(menu?.index ?? 0, choices.length - 1));
  const closeMenu = () => { setMenu(undefined); setFocus('input'); };
  const choose = async (choice?: Choice) => {
    if (!menu || choice?.disabled) return;
    try {
      if (menu.kind === 'context') {
        if (choice?.key === 'web') { setWeb(current => !current); closeMenu(); }
        else if (choice) openMenu(choice.key as MenuKind);
      } else if (menu.kind === 'commands' && choice) {
        const text = `/${choice.key} `; setDraft({text, cursor: text.length}); closeMenu();
      } else if (menu.kind === 'model' && choice) {
        await backend.request('model', {model: choice.key}); closeMenu();
      } else if (menu.kind === 'effort' && choice) {
        await backend.request('effort', {effort: choice.key}); closeMenu();
      } else if (menu.kind === 'file') {
        const result = await backend.request<{path: string}>('file', {path: menu.input.text});
        setFiles(current => [...new Set([...current, result.path])]); closeMenu();
      }
    } catch (error) { setMenu(current => current ? {...current, error: error instanceof Error ? error.message : String(error)} : current); }
  };
  const respond = (approved: boolean) => {
    if (state.approval) void request('approve', {approvalId: state.approval.id, approved});
  };
  usePaste(text => {
    if (state.approval) return;
    if (menu && ['model', 'file', 'commands'].includes(menu.kind)) setMenu(current => current ? {...current, input: insert(current.input, text.replace(/[\r\n]+/g, ' ')), index: 0} : current);
    else if (!menu) { setFocus('input'); setDraft(current => insert(current, text)); }
  });
  useInput((input, key) => {
    if (key.eventType === 'release' || quitting.current) return;
    if (key.ctrl && input === 'q') { void quit(); return; }
    if (state.approval) {
      if (input === 'y') respond(true);
      else if (input === 'n' || key.escape || (key.ctrl && input === 'c')) respond(false);
      else if (key.tab || key.leftArrow || key.rightArrow) setApprovalChoice(current => !current);
      else if (key.return) respond(approvalChoice);
      else if (key.pageDown || key.downArrow) setApprovalScroll(current => current + (key.pageDown ? 8 : 1));
      else if (key.pageUp || key.upArrow) setApprovalScroll(current => Math.max(0, current - (key.pageUp ? 8 : 1)));
      return;
    }
    if (menu) {
      if (key.escape || (key.ctrl && input === 'c')) { closeMenu(); return; }
      if (menu.kind === 'agents' && input === 'c') { const agent = agents[selected]; if (agent?.parent_agent_id) void request('cancel_agent', {agentId: agent.agent_id}); return; }
      if (key.upArrow || key.downArrow) { setMenu({...menu, index: Math.max(0, Math.min(choices.length - 1, selected + (key.upArrow ? -1 : 1))), scroll: 0}); return; }
      if (key.pageUp || key.pageDown) { setMenu({...menu, scroll: Math.max(0, menu.scroll + (key.pageUp ? -5 : 5))}); return; }
      if (key.return || (key.tab && menu.kind === 'commands')) { void choose(choices[selected]); return; }
      if (['model', 'file', 'commands'].includes(menu.kind)) setMenu({...menu, input: edit(menu.input, input, key, columns - 12), index: 0, error: undefined});
      return;
    }
    if ((key.ctrl && input === 'c') || key.escape) {
      if (state.busy) void request('cancel');
      else if (key.ctrl) { setDraft(emptyDraft()); setFiles([]); setWeb(false); }
      return;
    }
    if (key.ctrl && input === 'p') { openMenu('commands'); return; }
    if (key.ctrl && input === 'g') { openMenu('agents'); return; }
    if (key.ctrl && input === 'o') { setExpanded(current => expandTools('latest', state, current)); return; }
    if (key.meta && ['o', 'a', 'c'].includes(input)) {
      const mode = input === 'o' ? 'group' : input === 'a' ? 'all' : 'none';
      setExpanded(current => expandTools(mode, state, current));
      setToast(input === 'o' ? 'Toggled latest tool group' : input === 'a' ? 'Expanded tool details' : 'Collapsed tool details');
      return;
    }
    if (key.ctrl && key.end) { setScroll(null); return; }
    if (key.pageUp || key.pageDown) { moveScroll((key.pageUp ? -1 : 1) * Math.max(1, dimensions.conversation - 2)); return; }
    if (key.meta && (key.upArrow || key.downArrow)) {
      if (historyIndex === null) savedDraft.current = draft;
      const next = Math.max(0, Math.min(history.length, (historyIndex ?? history.length) + (key.upArrow ? -1 : 1)));
      setHistoryIndex(next);
      const text = history[next]; setDraft(text === undefined ? savedDraft.current : {text, cursor: text.length}); return;
    }
    if (key.tab) { setFocus(focusOrder[(focusOrder.indexOf(focus) + (key.shift ? 4 : 1)) % focusOrder.length]!); return; }
    if ((key.return && (key.shift || key.meta)) || (key.ctrl && input === 'j') || input === '\n') { setDraft(current => insert(current, '\n')); setFocus('input'); return; }
    if (key.return) { if (focus === 'input' || focus === 'send') void submit(); else action(focus); return; }
    if (focus === 'input') {
      if (input === '/' && !draft.text) { openMenu('commands'); return; }
      setDraft(current => edit(current, input, key, dimensions.width - 6));
    }
  });

  let overlay: React.ReactNode;
  const panelWidth = Math.min(columns - 4, 72), panelHeight = Math.min(rows - 2, 24);
  if (state.approval) {
    const approval = state.approval;
    const body = [approval.description, approval.paths.join('\n'), approval.command, approval.diff || JSON.stringify(approval.params, null, 2)].filter(Boolean).join('\n\n');
    const preview = wrapAnsi(clean(body), Math.max(1, panelWidth - 6), {hard: true}).split('\n');
    const visible = Math.max(1, panelHeight - 7), start = Math.min(approvalScroll, Math.max(0, preview.length - visible));
    overlay = <Box flexDirection="column" width={panelWidth} height={panelHeight} paddingX={2} paddingY={1} backgroundColor={colors.menu} borderStyle="round" borderColor={colors.accent}>
      <Text bold color={colors.text}>{approval.dangerous ? '! ' : ''}Permission required · {approval.tool}</Text>
      <Box flexDirection="column" height={visible} marginY={1} overflow="hidden">{preview.slice(start, start + visible).map((line, index) => <Text key={index} color={line.startsWith('+') ? colors.text : line.startsWith('-') ? colors.dim : colors.muted} wrap="truncate">{line || ' '}</Text>)}</Box>
      <Box gap={3}><HitBox onClick={() => respond(false)}><Text inverse={!approvalChoice}> Reject [n] </Text></HitBox><HitBox onClick={() => respond(true)}><Text inverse={approvalChoice}> Approve [y] </Text></HitBox></Box>
    </Box>;
  } else if (menu?.kind === 'agents') {
    const record = agents[selected];
    const details = wrapAnsi(clean(record ? agentDetails(record) : 'No delegated agents yet.'), Math.max(1, panelWidth - 6), {hard: true}).split('\n');
    overlay = <Box flexDirection="column" width={panelWidth} height={panelHeight} paddingX={2} paddingY={1} backgroundColor={colors.menu} borderStyle="round" borderColor={colors.line}>
      <Text bold color={colors.text}>Agent activity</Text>
      {choices.slice(Math.max(0, selected - 3), Math.max(0, selected - 3) + 4).map(choice => <Text key={choice.key} color={choice.key === record?.agent_id ? colors.accent : colors.muted}>{fit(choice.label, panelWidth - 6)}</Text>)}
      <Box flexDirection="column" flexGrow={1} marginTop={1} overflow="hidden">{details.slice(menu.scroll, menu.scroll + Math.max(1, panelHeight - 9)).map((line, index) => <Text key={index} color={colors.muted}>{line || ' '}</Text>)}</Box>
      <Text color={colors.dim}>↑↓ select · c cancel · pgup/pgdn scroll · esc</Text>
    </Box>;
  } else if (menu) {
    overlay = <Menu title={{context: 'Add to your prompt', model: 'Choose a model', effort: 'Reasoning effort', file: 'Add a workspace file', commands: 'Commands'}[menu.kind]}
      choices={choices} selected={selected} input={['model', 'file', 'commands'].includes(menu.kind) ? menu.input : undefined}
      width={panelWidth} height={panelHeight} error={menu.error} onChoose={choice => { void choose(choice); }} onClose={closeMenu}/>;
  }
  return <TerminalView state={state} draft={draft} focus={focus} files={files} web={web} sending={sending} action={action}
    removeFiles={() => setFiles([])} removeWeb={() => setWeb(false)} columns={columns} rows={rows} lines={lines} scroll={scroll}
    toggle={toggle} toast={toast} overlay={overlay}/>;
}
