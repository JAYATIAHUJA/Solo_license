import assert from 'node:assert/strict';
import test from 'node:test';

import { flagRequest, flaggedTargets, levelChanges, levelsOf, pauseCause } from '../src/lib/coding-live.js';

const lic = (action_class, level, repo = 'app') => ({ repo, action_class, level });

test('levels are keyed by repository and action class', () => {
  assert.deepEqual(levelsOf([lic('file-edit', 1), lic('test', 2, 'api')]), { 'app:file-edit': 1, 'api:test': 2 });
  assert.deepEqual(levelsOf(null), {});
});

test('the first poll flashes nothing', () => {
  assert.deepEqual(levelChanges(null, { 'app:file-edit': 2 }), {});
});

test('a level that went up or down between polls is reported with its direction', () => {
  const before = { 'app:file-edit': 1, 'app:test': 2, 'app:install': 0 };
  const after = { 'app:file-edit': 2, 'app:test': 0, 'app:install': 0 };
  assert.deepEqual(levelChanges(before, after), { 'app:file-edit': 'up', 'app:test': 'down' });
});

test('a class seen for the first time is not a change', () => {
  assert.deepEqual(levelChanges({ 'app:file-edit': 1 }, { 'app:file-edit': 1, 'app:git': 0 }), {});
});

test('a flag names exactly one decision or one turn, with a trimmed reason', () => {
  assert.deepEqual(flagRequest({ decision_id: 7 }, '  deleted the wrong file '), { decision_id: 7, reason: 'deleted the wrong file' });
  assert.deepEqual(flagRequest({ turn_id: 3 }, 'rewrote the whole module'), { turn_id: 3, reason: 'rewrote the whole module' });
});

test('a flag without a reason is refused before it is sent', () => {
  assert.throws(() => flagRequest({ turn_id: 3 }, '   '), /Say what was wrong/);
  assert.throws(() => flagRequest({ turn_id: 3 }, undefined), /Say what was wrong/);
});

test('a flag needs one target', () => {
  assert.throws(() => flagRequest({}, 'wrong'), /decision or a turn/);
  assert.throws(() => flagRequest({ decision_id: 1, turn_id: 2 }, 'wrong'), /decision or a turn/);
});

test('flagged decisions and turns are known from the flags list', () => {
  const flagged = flaggedTargets([{ decision_id: 4, turn_id: null }, { decision_id: null, turn_id: 9 }]);
  assert.ok(flagged.decisions.has(4));
  assert.ok(flagged.turns.has(9));
  assert.equal(flagged.turns.has(4), false);
  assert.equal(flaggedTargets(undefined).decisions.size, 0);
});

const ev = (kind, action_class, extra = {}) => ({ repo: 'app', action_class, kind, actor_id: 'system:gate', reason: '', ...extra });

test("a class paused by a person's flag says who flagged it", () => {
  const events = [
    ev('promote', 'test'),
    ev('flag', 'file-edit', { actor_id: 'demo:jayati', reason: 'demo:jayati: wrong framework' }),
    ev('demote', 'file-edit'),
  ];
  assert.deepEqual(pauseCause(events, lic('file-edit', 0)), { flagged: true, actorId: 'demo:jayati' });
});

test('a class paused by a failure, or with no history, is not a flag', () => {
  const events = [ev('demote', 'file-edit'), ev('flag', 'file-edit', { actor_id: 'demo:jayati' })];
  assert.deepEqual(pauseCause(events, lic('file-edit', 0)), { flagged: false, actorId: '' });
  assert.deepEqual(pauseCause(undefined, lic('file-edit', 0)), { flagged: false, actorId: '' });
  assert.deepEqual(pauseCause([ev('flag', 'file-edit', { repo: 'other' })], lic('file-edit', 0)), { flagged: false, actorId: '' });
});

test("flagging one decision does not mark its whole turn as flagged", () => {
  const flagged = flaggedTargets([{ decision_id: 4, turn_id: 2 }]);
  assert.ok(flagged.decisions.has(4));
  assert.equal(flagged.turns.has(2), false);
});
