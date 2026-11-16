import type {ServerMessage, Settings, Transport} from './protocol.js';

export class DemoBackend implements Transport {
  private listeners = new Set<(message: ServerMessage) => void>();
  private timers: ReturnType<typeof setTimeout>[] = [];
  private settings: Settings = {model: 'demo/postal', cwd: '~/workspace/postal', approval: 'ask',
    reasoning: {enabled: true, visible: true, effort: 'medium', max_tokens: null}};
  private emit(message: ServerMessage) { for (const listener of this.listeners) listener(message); }
  subscribe(listener: (message: ServerMessage) => void) {
    this.listeners.add(listener);
    queueMicrotask(() => listener({type: 'ready', settings: this.settings, history: [], messages: [], version: 'preview',
      logo: ['    ██████      ', '  ████████████  ', '████████████████'], capabilities: {read: false, search: false},
      commands: [{name: 'help', description: 'Show help'}, {name: 'clear', description: 'Start a fresh conversation'}]}));
    return () => { this.listeners.delete(listener); };
  }
  async request<T = Record<string, unknown>>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    if (method === 'model') this.settings = {...this.settings, model: String(params.model)};
    if (method === 'effort') this.settings = {...this.settings, reasoning: {...this.settings.reasoning, effort: String(params.effort)}};
    if (method === 'model' || method === 'effort') this.emit({type: 'settings', settings: this.settings});
    if (method === 'submit') {
      const text = String(params.text);
      if (text === '/clear') this.emit({type: 'transcript', messages: []});
      else {
        this.emit({type: 'turn_start', text, files: [], web: false});
        const parts = ['The frontend is now **React + TypeScript**.\n\n', 'Python still owns the agent, tools, sessions, and approvals.\n\n', 'Try **Tab** to focus the prompt controls, **Ctrl+P** for commands, or **Ctrl+Q** to quit.'];
        parts.forEach((content, index) => this.timers.push(setTimeout(() => this.emit({type: 'agent_event', event: {type: 'text_delta', agent_id: 'main', parent_agent_id: null, data: {content}}}), 350 * (index + 1))));
        this.timers.push(setTimeout(() => this.emit({type: 'turn_end', status: 'Ready'}), 1500));
      }
    }
    if (method === 'cancel') { this.timers.forEach(clearTimeout); this.emit({type: 'turn_end', status: 'Interrupted'}); }
    return {} as T;
  }
  async close() { this.timers.forEach(clearTimeout); }
}
