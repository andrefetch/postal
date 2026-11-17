import type {Approval, ServerMessage, Settings} from './protocol.js';
import {finishAgents, updateAgent, type AgentActivity} from './agents.js';
export interface Block {
  id: number; kind: 'user' | 'assistant' | 'notice' | 'reasoning' | 'tool' | 'agent'; text: string; agentId?: string;
  title?: string; callId?: string; status?: string; args?: Record<string, unknown>; files?: string[]; web?: boolean;
  startedAt?: number; finishedAt?: number;
  error?: string; exitCode?: number; diff?: string; output?: string;
  metadata?: Record<string, unknown>; truncated?: boolean;
}
export interface State {
  ready: boolean; busy: boolean; status: string; settings: Settings; blocks: Block[]; logo: string[];
  commands: {name: string; description: string}[]; history: string[]; version: string;
  capabilities: {read: boolean; search: boolean}; agents: Record<string, AgentActivity>; approval?: Approval;
  nextId: number; assistant?: number; reasoning?: number; tokens: number; recentModels: string[];
  turnStartedAt?: number;
}
export const CLOUD_LOGO = ['      ████████        ', '    ██████████████    ', '  ██████████████████  ', '██████████████████████'];
export const initialState: State = {
  ready: false, busy: false, status: 'Connecting', blocks: [], commands: [], history: [], nextId: 0, tokens: 0,
  version: '', capabilities: {read: false, search: false}, agents: {}, recentModels: [],
  logo: CLOUD_LOGO,
  settings: {model: '', cwd: '', approval: 'on_request', reasoning: {enabled: true, visible: true, effort: null, max_tokens: null}},
};
export function reduce(state: State, message: ServerMessage): State {
  const now = Date.now();
  const add = (block: Omit<Block, 'id'>): State => ({...state, nextId: state.nextId + 1, blocks: [...state.blocks, {...block, id: state.nextId}]});
  switch (message.type) {
    case 'ready': return {...state, ...message, ready: true, status: 'Ready', recentModels: [message.settings.model],
      blocks: message.messages.map((block, id) => ({id, kind: block.role, text: block.text})), nextId: message.messages.length};
    case 'settings': return {...state, settings: message.settings,
      recentModels: [...new Set([...state.recentModels, message.settings.model])]};
    case 'transcript': return {...state, blocks: message.messages.map((block, id) => ({id, kind: block.role, text: block.text})),
      nextId: message.messages.length, assistant: undefined, reasoning: undefined, agents: {}};
    case 'turn_start': return {...add({kind: 'user', text: message.text, files: message.files, web: message.web}),
      busy: true, status: 'Thinking', assistant: undefined, reasoning: undefined, turnStartedAt: now};
    case 'turn_end': return {...state, busy: false, status: message.status, assistant: undefined, reasoning: undefined,
      agents: finishAgents(state.agents, message.status === 'Interrupted' ? 'cancelled' : message.status === 'Ready' ? 'completed' : 'failed'),
      blocks: state.blocks.map(block => block.status === 'running' ? {...block, status: message.status === 'Interrupted' ? 'cancelled' : message.status === 'Ready' ? 'completed' : 'failed', finishedAt: now} : block)};
    case 'notice': return add({kind: 'notice', text: message.text});
    case 'fatal': {
      const next = add({kind: 'notice', text: message.message});
      return {...next, ready: false, busy: false, status: 'Disconnected', agents: finishAgents(state.agents, 'failed'),
        blocks: next.blocks.map(block => block.status === 'running' ? {...block, status: 'failed', finishedAt: now} : block)};
    }
    case 'approval': return {...state, approval: message.approval};
    case 'approval_closed': return {...state, approval: state.approval?.id === message.id ? undefined : state.approval};
    case 'agent_event': {
      const {event} = message, data = event.data;
      if (event.type === 'agent_status' || (event.agent_id && event.agent_id !== 'main')) {
        const id = event.type === 'agent_status' ? data.agent_id : event.agent_id!;
        const agent = updateAgent(state.agents[id], {...event, agent_id: id});
        // Child prose stays private; only activity and final results belong in the agent view.
        if (event.type === 'text_delta' && !state.agents[id]) return state;
        const next = id !== 'main' && !state.blocks.some(block => block.agentId === id)
          ? add({kind: 'agent', agentId: id, text: ''}) : state;
        return {...next, agents: {...state.agents, [id]: agent}};
      }
      if (event.type === 'text_delta' || event.type === 'reasoning_delta') {
        const reasoning = event.type === 'reasoning_delta';
        if (reasoning && !state.settings.reasoning.visible) return state;
        const key = reasoning ? 'reasoning' : 'assistant', id = state[key];
        if (id === undefined) return {...add({kind: reasoning ? 'reasoning' : 'assistant', text: data.content ?? '', ...(reasoning ? {status: 'running', startedAt: now} : {})}),
          [key]: state.nextId, status: reasoning ? 'Thinking' : 'Responding'};
        return {...state, blocks: state.blocks.map(block => block.id === id ? {...block, text: block.text + (data.content ?? '')} : block)};
      }
      if (event.type === 'text_complete') return {...state, assistant: undefined};
      if (event.type === 'reasoning_complete') return {...state, reasoning: undefined,
        blocks: state.blocks.map(block => block.id === state.reasoning ? {...block, status: 'completed', finishedAt: now} : block)};
      if (event.type === 'tool_call_start') return {...add({kind: 'tool', title: data.name, args: data.arguments,
        callId: data.call_id, status: 'running', text: '', startedAt: now}), status: `Running ${data.name}`};
      if (event.type === 'tool_progress' || event.type === 'tool_call_complete') return {...state,
        blocks: state.blocks.map(block => block.callId === data.call_id ? {...block,
          text: event.type === 'tool_progress' ? (block.text + (data.content ?? '')).slice(-12000) :
            [data.output, data.error, data.diff].filter(Boolean).join('\n'),
          ...(event.type === 'tool_call_complete' ? {finishedAt: now, output: data.output ?? "", metadata: data.metadata ?? {}, truncated: data.truncated, error: data.error, exitCode: typeof data.exit_code === 'number' ? data.exit_code : undefined, diff: data.diff} : {}),
          status: event.type === 'tool_progress' ? 'running' : data.success ? 'completed' : 'failed'} : block)};
      if (event.type === 'usage') return {...state, tokens: data.usage?.total_tokens ?? state.tokens};
      if (event.type === 'agent_error') return {...add({kind: 'notice', text: data.error ?? 'Agent failed'}), status: 'Failed'};
      return state;
    }
    default: return state;
  }
}
