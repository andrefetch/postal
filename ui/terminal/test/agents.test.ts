import assert from 'node:assert/strict';
import {test} from 'node:test';
import {initialState, reduce} from '../src/state.js';
import {conversationLines} from '../src/components.js';
import {agentDetails} from '../src/agents.js';
import type {AgentEvent} from '../src/protocol.js';

test('interleaved subagent tools and progress are attributed to each agent and survive snapshots', () => {
  let state = reduce(initialState, {type: 'turn_start', text: 'review', files: [], web: false});
  const event = (agent_id: string, type: string, data: AgentEvent['data']) => {
    state = reduce(state, {type: 'agent_event', event: {agent_id, parent_agent_id: 'main', type, data}});
  };
  for (const [id, name] of [['a', 'Researcher'], ['b', 'Reviewer']]) {
    event(id!, 'agent_status', {agent_id: id, parent_agent_id: 'main', depth: 1, name, goal: 'Inspect the relevant files', status: 'running'});
  }
  event('a', 'tool_call_start', {call_id: 'same', name: 'grep', arguments: {pattern: 'auth'}});
  event('b', 'tool_call_start', {call_id: 'same', name: 'read', arguments: {path: 'routes.py'}});
  event('a', 'tool_progress', {call_id: 'same', content: 'Searching authentication'});
  event('b', 'tool_progress', {call_id: 'same', content: 'Reading routes'});
  event('a', 'text_delta', {content: 'Private chain of thought'});
  event('a', 'agent_status', {agent_id: 'a', status: 'waiting_for_children'});
  assert.equal(state.agents.a!.tools[0]!.output, 'Searching authentication');
  assert.equal(state.agents.b!.tools[0]!.output, 'Reading routes');
  assert.equal(state.blocks.filter(block => block.kind === 'agent').length, 2);
  const lines = conversationLines(state.blocks, 80, new Set(), state);
  const text = lines.map(line => line.text).join('\n');
  for (const expected of ['Researcher', 'Reviewer', 'grep auth', 'read routes.py', 'Searching authentication', 'Reading routes']) assert.ok(text.includes(expected), expected);
  assert.ok(!text.includes('Private chain of thought'));
  assert.equal(lines.filter(line => line.activity && (line.text.includes('grep') || line.text.includes('read'))).length, 2);
  event('a', 'tool_call_complete', {call_id: 'same', success: false, error: 'Search failed'});
  assert.equal(state.agents.a!.tools[0]!.status, 'failed');
  assert.equal(state.agents.b!.tools[0]!.status, 'running');
  event('b', 'tool_call_complete', {call_id: 'same', success: true, output: 'Routes found'});
  event('b', 'usage', {usage: {total_tokens: 1234}});
  event('b', 'agent_status', {agent_id: 'b', status: 'completed', result: 'Review completed'});
  assert.match(agentDetails(state.agents.b!), /read  routes.py/);
  assert.match(agentDetails(state.agents.b!), /Routes found/);
  assert.match(agentDetails(state.agents.b!), /1,234 tokens/);
  const expanded = new Set(state.blocks.filter(block => block.kind === 'agent').map(block => block.id));
  assert.ok(conversationLines(state.blocks, 80, expanded, state).some(line => line.text.includes('Review completed')));
  state = reduce(state, {type: 'turn_end', status: 'Ready'});
  state = reduce(state, {type: 'turn_start', text: 'follow up', files: [], web: false});
  assert.ok(conversationLines(state.blocks, 80, expanded, state).some(line => line.text.includes('Review completed')));
});

test('subagent history stays bounded and terminal snapshots stop unfinished tools', () => {
  let state = initialState;
  const event = (type: string, data: AgentEvent['data']) => {
    state = reduce(state, {type: 'agent_event', event: {agent_id: 'child', parent_agent_id: 'main', type, data}});
  };
  for (let index = 0; index < 25; index++) event('tool_call_start', {call_id: String(index), name: 'read', arguments: {path: `file${index}`}});
  event('tool_progress', {call_id: '24', content: 'x'.repeat(10000)});
  assert.equal(state.agents.child!.tools.length, 20);
  assert.equal(state.agents.child!.tools.at(-1)!.output.length, 4000);
  event('agent_status', {agent_id: 'child', status: 'cancelled'});
  assert.ok(state.agents.child!.tools.every(tool => tool.status === 'cancelled'));
});
