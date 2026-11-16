import assert from 'node:assert/strict';
import {test} from 'node:test';
import {initialState, reduce} from '../src/state.js';
test('child output stays out of the main transcript and tool updates stay correlated', () => {
  let state = reduce(initialState, {type: 'turn_start', text: 'inspect', files: [], web: false});
  state = reduce(state, {type: 'agent_event', event: {type: 'text_delta', data: {content: 'private child'}, agent_id: 'child', parent_agent_id: 'main'}});
  assert.equal(state.blocks.length, 1);
  state = reduce(state, {type: 'agent_event', event: {type: 'tool_call_start', data: {call_id: 'one', name: 'read', arguments: {path: 'app.py'}}, agent_id: 'main', parent_agent_id: null}});
  state = reduce(state, {type: 'agent_event', event: {type: 'tool_call_complete', data: {call_id: 'one', success: true, output: 'contents'}, agent_id: 'main', parent_agent_id: null}});
  assert.equal(state.blocks[1]!.status, 'completed');
  assert.equal(state.blocks[1]!.text, 'contents');
  state = reduce(state, {type: 'turn_end', status: 'Ready'});
  assert.equal(state.busy, false);
});
