import assert from 'node:assert/strict';
import test from 'node:test';

import { flagReason, flagSentence, personName } from '../src/lib/ledger-words.js';

const flag = {
  kind: 'flag',
  task_class: 'file-edit@shop',
  from_level: 2,
  to_level: 0,
  actor_id: 'demo:jayati',
  reason: 'demo:jayati: deleted the migrations folder',
};

test('people are named from their actor id', () => {
  assert.equal(personName('human:jayati-ahuja'), 'Jayati Ahuja');
  assert.equal(personName('system:gate'), 'Solo License');
  assert.equal(personName(''), '');
});

test('a flag reads as a person saying the class was wrong', () => {
  assert.equal(flagSentence(flag), 'Jayati flagged file-edit in shop as wrong — back to L0');
});

test("a flag's reason drops the actor prefix the gate stores", () => {
  assert.equal(flagReason(flag), 'deleted the migrations folder');
  assert.equal(flagReason({ ...flag, reason: 'no prefix here' }), 'no prefix here');
  assert.equal(flagReason({ ...flag, reason: null }), '');
});

test('a flagged MCP server is named, not keyed', () => {
  assert.equal(flagSentence({ ...flag, task_class: 'mcp:github@shop' }), 'Jayati flagged GitHub (MCP) in shop as wrong — back to L0');
});

test('a flag without a known person still reads', () => {
  assert.equal(flagSentence({ ...flag, actor_id: '' }), 'Someone flagged file-edit in shop as wrong — back to L0');
});
