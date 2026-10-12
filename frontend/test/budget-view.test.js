import assert from 'node:assert/strict';
import test from 'node:test';

import { capMeter, sessionStatus, sourceWords, totals, usd } from '../src/lib/budget-view.js';

test('money shows cents, and a missing cap shows a dash', () => {
  assert.equal(usd(1.2), '$1.20');
  assert.equal(usd(null), '-');
});

test('the meter follows the warn line and stops at full', () => {
  assert.deepEqual(capMeter(0.5, 1, 0.8), { share: 0.5, tone: 'ok', label: 'Under the cap' });
  assert.equal(capMeter(0.85, 1, 0.8).tone, 'wait');
  assert.deepEqual(capMeter(1.2, 1, 0.8), { share: 1, tone: 'bad', label: 'Cap reached' });
  assert.equal(capMeter(3, null).label, 'No cap');
});

test('a session row says why it stopped, or that a person resumed it', () => {
  assert.equal(sessionStatus({ blocked: true, scope: 'session', state: 'cap' }).label, 'Stopped: session cap');
  assert.equal(sessionStatus({ blocked: true, scope: 'day', state: 'cap' }).label, "Stopped: today's cap");
  assert.equal(sessionStatus({ blocked: false, state: 'cap' }).label, 'Resumed by a person');
  assert.equal(sessionStatus({ state: 'warn' }).tone, 'wait');
  assert.equal(sessionStatus({ state: 'ok' }).tone, 'ok');
  assert.equal(sessionStatus({ state: 'ok', usd: 1.24 }, 1).label, 'Resumed by a person');
  assert.equal(sessionStatus({ state: 'ok', usd: 0.4 }, 1).label, 'Under the cap');
});

test('the source of a figure is said in words', () => {
  assert.equal(sourceWords('reported'), "the agent's own figure");
  assert.equal(sourceWords('estimate'), 'estimated from tokens at list price');
  assert.equal(sourceWords('unknown'), 'not reported');
});

test('totals add today across repositories and set it against the time saved', () => {
  const t = totals({
    repos: [{ day_usd: 1.5 }, { day_usd: 0.5 }],
    sessions: [{ blocked: true }, { blocked: false }],
    savings: { usd_saved: 12 },
  });
  assert.deepEqual(t, { spentToday: 2, saved: 12, stopped: 1, net: 10 });
  assert.deepEqual(totals(null), { spentToday: 0, saved: 0, stopped: 0, net: 0 });
});
