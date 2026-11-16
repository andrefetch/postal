import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process';
import {createInterface} from 'node:readline';
import type {ServerMessage, Transport} from './protocol.js';

export class PythonBackend implements Transport {
  private child: ChildProcessWithoutNullStreams;
  private listeners = new Set<(message: ServerMessage) => void>();
  private backlog: ServerMessage[] = [];
  private pending = new Map<number, {resolve: (value: any) => void; reject: (error: Error) => void}>();
  private nextId = 0;
  private closing = false;
  private exited = false;
  private stderr = '';
  private exitPromise: Promise<void>;

  constructor(python: string, bootstrap: Record<string, unknown>) {
    this.child = spawn(python, ['-u', '-m', 'ui.bridge'], {
      stdio: ['pipe', 'pipe', 'pipe'], detached: process.platform !== 'win32',
      env: {...process.env, PYTHONUNBUFFERED: '1'},
    });
    this.child.stderr.setEncoding('utf8');
    this.child.stderr.on('data', (chunk: string) => { this.stderr = (this.stderr + chunk).slice(-4000); });
    this.child.stdin.on('error', () => {}); // The process error/exit handlers report transport failures.
    const lines = createInterface({input: this.child.stdout});
    lines.on('line', line => {
      try {
        const message = JSON.parse(line);
        if (!message || typeof message.type !== 'string') throw new Error('Invalid Python message');
        if (message.type === 'result' || message.type === 'error') {
          const pending = this.pending.get(message.id);
          if (!pending) return;
          this.pending.delete(message.id);
          if (message.type === 'error') pending.reject(new Error(message.message));
          else pending.resolve(message.result);
        } else this.emit(message as ServerMessage);
      } catch (error) {
        this.emit({type: 'fatal', message: `Invalid backend response: ${String(error)}`});
      }
    });
    this.exitPromise = new Promise(resolve => {
      this.child.once('error', error => {
        this.fail(error);
        resolve();
      });
      this.child.once('close', code => {
        this.exited = true;
        lines.close();
        this.fail(new Error(`Python backend exited (${code ?? 'signal'}).${this.stderr ? `\n${this.stderr.trim()}` : ''}`));
        resolve();
      });
    });
    void this.request('init', bootstrap).catch(error => this.emit({type: 'fatal', message: error.message}));
  }

  private fail(error: Error) {
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
    if (!this.closing) this.emit({type: 'fatal', message: error.message});
  }

  private emit(message: ServerMessage) {
    if (!this.listeners.size) this.backlog.push(message);
    else for (const listener of this.listeners) listener(message);
  }

  subscribe(listener: (message: ServerMessage) => void) {
    this.listeners.add(listener);
    for (const message of this.backlog.splice(0)) listener(message);
    return () => { this.listeners.delete(listener); };
  }

  request<T = Record<string, unknown>>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    if (this.exited || this.child.stdin.destroyed) return Promise.reject(new Error('Python backend is disconnected.'));
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, {resolve, reject});
      this.child.stdin.write(JSON.stringify({id, method, params}) + '\n', error => {
        if (error) { this.pending.delete(id); reject(error); }
      });
    });
  }

  terminate(signal: NodeJS.Signals = 'SIGTERM') {
    if (this.exited || !this.child.pid) return;
    try {
      if (process.platform === 'win32') this.child.kill(signal);
      else process.kill(-this.child.pid, signal);
    } catch { /* It may already have exited. */ }
  }

  async close() {
    if (this.closing) return this.exitPromise;
    this.closing = true;
    const timer = setTimeout(() => this.terminate(), 5000);
    const kill = setTimeout(() => this.terminate('SIGKILL'), 6500);
    try {
      await this.request('quit').catch(() => {});
      this.child.stdin.end();
      await this.exitPromise;
    } finally { clearTimeout(timer); clearTimeout(kill); }
  }
}
