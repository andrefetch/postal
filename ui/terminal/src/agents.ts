import type {AgentEvent, AgentRecord} from './protocol.js';
import {toolDetails} from './toolPresentation.js';

export interface AgentTool {
  callId: string; name: string; args: Record<string, unknown>;
  status: 'running' | 'completed' | 'failed' | 'cancelled'; output: string;
  startedAt?: number; finishedAt?: number; error?: string; exitCode?: number; diff?: string;
  metadata?: Record<string, unknown>; truncated?: boolean;
}
export interface AgentActivity extends AgentRecord {tools: AgentTool[]; phase: string}
export const agentFinished = (status: string) => ['completed', 'failed', 'cancelled', 'timed_out'].includes(status);

export function finishAgents(agents: Record<string, AgentActivity>, status: string) {
  return Object.fromEntries(Object.entries(agents).map(([id, agent]) => [id, agentFinished(agent.status) ? agent
    : updateAgent(agent, {type: 'agent_status', agent_id: id, parent_agent_id: agent.parent_agent_id, data: {status}})]));
}

export function updateAgent(previous: AgentActivity | undefined, event: AgentEvent): AgentActivity {
  const {data, type} = event;
  let agent: AgentActivity = previous ?? {
    agent_id: event.agent_id!, parent_agent_id: event.parent_agent_id ?? 'main',
    name: event.agent_id!, goal: '', depth: 1, status: 'running', tools: [], phase: 'Thinking…',
  };
  if (type === 'agent_status') {
    agent = {...agent, ...data};
  }
  if (type === 'tool_call_start') agent = {...agent, phase: `Running ${data.name}`, tools: [
    ...agent.tools.filter(tool => tool.callId !== data.call_id),
    {callId: data.call_id, name: data.name, args: data.arguments ?? {}, status: 'running', output: '', startedAt: Date.now()} as AgentTool,
  ].slice(-20)};
  if (type === 'tool_progress' || type === 'tool_call_complete') {
    if (!agent.tools.some(tool => tool.callId === data.call_id)) agent = {...agent, tools: [...agent.tools,
      {callId: data.call_id, name: data.name ?? 'Tool', args: {}, status: 'running', output: ''}].slice(-20) as AgentTool[]};
    agent = {...agent, phase: type === 'tool_call_complete' ? 'Thinking…' : agent.phase, tools: agent.tools.map(tool =>
      tool.callId !== data.call_id ? tool : {...tool,
        status: type === 'tool_progress' ? 'running' : data.success ? 'completed' : 'failed',
        ...(type === 'tool_call_complete' ? {finishedAt: Date.now(), metadata: data.metadata ?? {}, truncated: data.truncated, error: data.error, exitCode: typeof data.exit_code === 'number' ? data.exit_code : undefined, diff: data.diff} : {}),
        output: type === 'tool_progress' ? tool.output + (data.content ?? '') : (data.output ?? tool.output),
      })};
  }
  if (type === 'reasoning_delta') agent = {...agent, phase: 'Thinking…'};
  if (type === 'text_delta') agent = {...agent, phase: 'Responding…'};
  if (type === 'usage') agent = {...agent, usage: data.usage};
  if (type === 'agent_error') agent = {...agent, status: 'failed', error: data.error};
  if (agentFinished(agent.status)) agent = {...agent, phase: agent.status.replaceAll('_', ' '), tools: agent.tools.map(tool => tool.status === 'running'
    ? {...tool, finishedAt: Date.now(), status: agent.status === 'completed' ? 'completed' : agent.status === 'failed' ? 'failed' : 'cancelled'} : tool)};
  return agent;
}

export function toolLabel(tool: AgentTool) {
  const target = tool.args.command ?? tool.args.path ?? tool.args.pattern ?? tool.args.query ??
    Object.values(tool.args).find(value => typeof value === 'string') ?? '';
  return `${tool.name}${target ? `  ${String(target)}` : ''}`;
}

export function agentDetails(agent: AgentActivity) {
  return [agent.goal, `Status: ${agent.status.replaceAll('_', ' ')} · ${agent.phase}`,
    ...agent.tools.map(tool => `${tool.status === 'running' ? '◌' : tool.status === 'completed' ? '✓' : '×'} ${toolLabel(tool)} · ${tool.status}\n${toolDetails(tool)}`),
    agent.error || agent.result || '', agent.usage?.total_tokens ? `${agent.usage.total_tokens.toLocaleString()} tokens` : '',
  ].filter(Boolean).join('\n\n');
}
