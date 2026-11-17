import assert from 'node:assert/strict';
import {test} from 'node:test';
import {initialState, reduce} from '../src/state.js';
import {conversationLines} from '../src/components.js';
import {agentDetails} from '../src/agents.js';
import {conversationToolGroups, expandTools, toggleDetail} from '../src/toolNavigation.js';
import {agentToolKey, toolSummary, type DetailKey} from '../src/toolPresentation.js';
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
  assert.equal(state.agents.child!.tools.at(-1)!.output.length, 10000);
  event('agent_status', {agent_id: 'child', status: 'cancelled'});
  assert.ok(state.agents.child!.tools.every(tool => tool.status === 'cancelled'));
});

test('opening an agent answer leaves individual tools and groups independently collapsible', () => {
  let state = initialState;
  const event = (type: string, data: AgentEvent['data']) => {
    state = reduce(state, {type: 'agent_event', event: {agent_id: 'child', parent_agent_id: 'main', type, data}});
  };
  for (const id of ['1', '2']) {
    event('tool_call_start', {call_id: id, name: 'read', arguments: {path: `file${id}`}});
    event('tool_call_complete', {call_id: id, success: true, output: `Full result ${id}`});
  }
  event('agent_status', {agent_id: 'child', status: 'completed', result: 'Agent final answer'});
  const now = Date.now() + 10000, heading = state.blocks[0]!.id;
  const group = conversationToolGroups(state.blocks, state.agents)[0]!;
  let expanded: Set<DetailKey> = toggleDetail(heading, state, new Set(), now);
  const lines = () => conversationLines(state.blocks, 80, expanded, {...state, now});
  const text = () => lines().map(line => line.text).join('\n');
  assert.match(text(), /Agent final answer/);
  assert.ok(!text().includes('Full result'));
  assert.equal(lines().find(line => line.group)!.tool!.expanded, false);
  expanded = expandTools('group', state, expanded, now);
  assert.equal(lines().find(line => line.group)!.tool!.expanded, true);
  const key = agentToolKey('child', '2');
  expanded = toggleDetail(key, state, expanded, now);
  assert.match(text(), /Full result 2/);
  expanded = toggleDetail(key, state, expanded, now);
  assert.ok(!text().includes('Full result 2'), 'click closes details with agent answer open');
  expanded = expandTools('latest', state, expanded, now);
  assert.match(text(), /Full result 2/);
  expanded = expandTools('latest', state, expanded, now);
  assert.ok(!text().includes('Full result 2'), 'Ctrl+O closes details with agent answer open');
  expanded = expandTools('group', state, expanded, now);
  assert.equal(lines().find(line => line.detailKey === group.key)!.tool!.expanded, false);
  assert.ok(!text().includes('read file2'), 'Alt+O closes the group with agent answer open');
  assert.match(text(), /Agent final answer/);
  expanded = expandTools('none', state, expanded, now);
  assert.match(text(), /Agent final answer/, 'collapsing tools preserves the separate answer expansion');
});

test('large child results remain complete in expanded rows, summaries, and the agent view', () => {
  let state = initialState;
  const event = (type: string, data: AgentEvent['data']) => {
    state = reduce(state, {type: 'agent_event', event: {agent_id: 'child', parent_agent_id: 'main', type, data}});
  };
  const output = Array.from({length: 500}, (_, i) => `Original result line ${i}`).join('\n');
  event('tool_call_start', {call_id: 'read', name: 'read', arguments: {path: 'large.txt'}});
  event('tool_progress', {call_id: 'read', content: output.slice(0, 5000)});
  event('tool_progress', {call_id: 'read', content: output.slice(5000)});
  assert.equal(state.agents.child!.tools[0]!.output, output);
  event('tool_call_complete', {call_id: 'read', success: true, output, truncated: false});
  const tool = state.agents.child!.tools[0]!;
  assert.equal(tool.output, output);
  assert.equal(toolSummary(tool), 'Read 500 lines');
  const text = conversationLines(state.blocks, 80, new Set([agentToolKey('child', 'read')]), state).map(line => line.text).join('\n');
  for (const line of output.split('\n')) assert.ok(text.includes(line), line);
  assert.ok(agentDetails(state.agents.child!).includes(output));
  event('tool_call_complete', {call_id: 'read', success: true, truncated: true});
  assert.equal(state.agents.child!.tools[0]!.output, output, 'a completion without output retains streamed text');
  assert.match(toolSummary(state.agents.child!.tools[0]!), /output truncated/);
});
