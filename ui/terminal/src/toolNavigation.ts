import type {Block, State} from './state.js';
import {agentToolKey, closedGroupKey, groupExpanded, groupTools, type DetailKey, type ToolActivity, type ToolGroup} from './toolPresentation.js';

export function mainTool(block: Block): ToolActivity {
  return {name: block.title ?? 'Tool', args: block.args ?? {}, status: block.status ?? 'completed', output: block.output ?? block.text,
    startedAt: block.startedAt, finishedAt: block.finishedAt, error: block.error, exitCode: block.exitCode, diff: block.diff,
    metadata: block.metadata, truncated: block.truncated};
}

export function conversationToolGroups(blocks: Block[], agents: State['agents']): ToolGroup[] {
  const groups: ToolGroup[] = [];
  for (let index = 0; index < blocks.length; index++) {
    const block = blocks[index]!;
    if (block.kind === 'tool') {
      const run = [block];
      while (blocks[index + 1]?.kind === 'tool') run.push(blocks[++index]!);
      groups.push(...groupTools(run.map(item => ({key: item.id, activity: mainTool(item)}))));
    } else if (block.kind === 'agent') {
      const agent = agents[block.agentId!];
      if (agent) groups.push(...groupTools(agent.tools.map(tool => ({key: agentToolKey(agent.agent_id, tool.callId), activity: tool})), agent.agent_id));
    }
  }
  return groups;
}

export function expandTools(mode: 'latest' | 'group' | 'all' | 'none', state: Pick<State, 'blocks' | 'agents'>,
  expanded: ReadonlySet<DetailKey>, now = Date.now()): Set<DetailKey> {
  const groups = conversationToolGroups(state.blocks, state.agents), next = new Set(expanded);
  if (mode === 'none') {
    const closed = new Set<DetailKey>(groups.filter(group => group.items.length > 1).map(group => closedGroupKey(group.key)));
    for (const block of state.blocks) if (block.kind === 'reasoning' && block.status === 'running') closed.add(-block.id - 1);
    return closed;
  }
  if (mode === 'all') {
    for (const group of groups) {
      next.add(group.key); next.delete(closedGroupKey(group.key));
      for (const item of group.items) next.add(item.key);
    }
    for (const block of state.blocks) if (block.kind === 'reasoning') {
      if (block.status === 'running') next.delete(-block.id - 1); else next.add(block.id);
    }
    return next;
  }
  if (mode === 'group') {
    const group = groups.filter(group => group.items.length > 1).sort((a, b) =>
      Math.max(...a.items.map(item => item.activity.startedAt ?? 0)) - Math.max(...b.items.map(item => item.activity.startedAt ?? 0))).at(-1);
    if (!group) return next;
    if (groupExpanded(group, next, now)) { next.delete(group.key); next.add(closedGroupKey(group.key)); }
    else { next.add(group.key); next.delete(closedGroupKey(group.key)); }
    return next;
  }
  const candidates: {key: DetailKey; time: number; group?: ToolGroup}[] = groups.flatMap(group => group.items.map(item => ({key: item.key, time: item.activity.startedAt ?? 0, group})));
  for (const block of state.blocks) if (block.kind === 'reasoning') candidates.push({key: block.status === 'running' ? -block.id - 1 : block.id,
    time: block.startedAt ?? 0});
  const latest = candidates.sort((a, b) => a.time - b.time).at(-1);
  if (!latest) return next;
  if (next.has(latest.key)) next.delete(latest.key); else next.add(latest.key);
  if (latest.group && latest.group.items.length > 1) { next.add(latest.group.key); next.delete(closedGroupKey(latest.group.key)); }
  return next;
}
