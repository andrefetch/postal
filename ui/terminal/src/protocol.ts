export interface Settings {
  model: string;
  cwd: string;
  approval: string;
  reasoning: {enabled: boolean; visible: boolean; effort: string | null; max_tokens: number | null};
}
export interface AgentRecord {
  agent_id: string; parent_agent_id: string | null; name: string; goal: string;
  status: string; result?: string; error?: string; depth: number;
  usage?: {total_tokens?: number};
}
export interface Approval {
  id: string; tool: string; description: string; params: Record<string, unknown>;
  command?: string; diff?: string; paths: string[]; dangerous: boolean;
}
export interface AgentEvent {
  type: string; data: Record<string, any>; agent_id: string | null; parent_agent_id: string | null;
}
export interface SavedMessage {role: 'user' | 'assistant'; text: string}
export type ServerMessage =
  | {type: 'ready'; settings: Settings; history: string[]; messages: SavedMessage[]; logo: string[];
      version: string; commands: {name: string; description: string}[]; capabilities: {read: boolean; search: boolean}}
  | {type: 'settings'; settings: Settings}
  | {type: 'transcript'; messages: SavedMessage[]}
  | {type: 'turn_start'; text: string; files: string[]; web: boolean}
  | {type: 'turn_end'; status: string}
  | {type: 'agent_event'; event: AgentEvent}
  | {type: 'approval'; approval: Approval}
  | {type: 'approval_closed'; id: string}
  | {type: 'notice' | 'toast'; text: string}
  | {type: 'fatal'; message: string}
  | {type: 'open_agents' | 'exit'};
export interface Transport {
  subscribe(listener: (message: ServerMessage) => void): () => void;
  request<T = Record<string, unknown>>(method: string, params?: Record<string, unknown>): Promise<T>;
  close(): Promise<void>;
}
