import assert from 'node:assert/strict';
import test from 'node:test';

import { byTurn, loopBadge, remediationView } from '../src/lib/coding-guidance.js';

test('rows are grouped by turn, oldest first, and rows without a turn are left out', () => {
  const grouped = byTurn([{ id: 3, turn_id: 1 }, { id: 2, turn_id: 2 }, { id: 1, turn_id: 1 }, { id: 4, turn_id: null }]);
  assert.deepEqual(grouped.get(1).map((r) => r.id), [1, 3]);
  assert.deepEqual(grouped.get(2).map((r) => r.id), [2]);
  assert.equal(grouped.has(null), false);
  assert.equal(byTurn(undefined).size, 0);
});

test('rows without a numeric id keep their order', () => {
  const grouped = byTurn([{ id: 'halt-s1', turn_id: 5 }, { id: 'decision-2', turn_id: 5 }]);
  assert.deepEqual(grouped.get(5).map((r) => r.id), ['halt-s1', 'decision-2']);
});

test('a delivered remediation reads as what the agent was told', () => {
  const view = remediationView({ kind: 'flagged', text: 'Solo License: Your last turn was flagged.', delivered_at: '2026-10-12 08:00:00' });
  assert.equal(view.text, 'Your last turn was flagged.');
  assert.deepEqual(view.status, { label: 'Delivered', tone: 'ok' });
});

test('a queued remediation waits for the next prompt', () => {
  const view = remediationView({ kind: 'flagged', text: 'Revert it.', delivered_at: null });
  assert.equal(view.text, 'Revert it.');
  assert.deepEqual(view.status, { label: 'Waiting for the next prompt', tone: 'wait' });
});

test('no loop events, no badge', () => {
  assert.equal(loopBadge([]), null);
  assert.equal(loopBadge(undefined), null);
});

test('a session halted right now outranks everything', () => {
  const badge = loopBadge([{ kind: 'repeat', severity: 'warning' }, { kind: 'halt', severity: 'stop', reason: 'ran it 5 times' }]);
  assert.deepEqual(badge, { label: 'Halted: looping', tone: 'bad', title: 'ran it 5 times' });
});

test('a stop that is over reads as stopped', () => {
  const badge = loopBadge([{ kind: 'loop-stop', severity: 'stop', reason: 'same call 5 times' }]);
  assert.deepEqual(badge, { label: 'Stopped: looping', tone: 'bad', title: 'same call 5 times' });
});

test('warnings are counted', () => {
  assert.deepEqual(loopBadge([{ kind: 'repeat', severity: 'warning', reason: 'a' }]),
    { label: 'Loop warning', tone: 'wait', title: 'a' });
  assert.deepEqual(loopBadge([{ kind: 'repeat', severity: 'warning', reason: 'a' }, { kind: 'same-failure', severity: 'warning', reason: 'b' }]),
    { label: '2 loop warnings', tone: 'wait', title: 'a\nb' });
});
