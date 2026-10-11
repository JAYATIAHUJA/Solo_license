import assert from 'node:assert/strict';
import test from 'node:test';

import { eventLinks } from '../src/lib/event-links.js';

test('an event with a neatlogs link and a checkpoint gets both links', () => {
  const links = eventLinks({
    neatlogs_link: 'https://app.neatlogs.com/traces/abc',
    entire_checkpoint: 'a3b2c4d5e6f7aa99',
  });
  assert.equal(links.trace, 'https://app.neatlogs.com/traces/abc');
  assert.deepEqual(links.checkpoint, {
    id: 'a3b2c4d5e6f7',
    explain: 'entire checkpoint explain a3b2c4d5e6f7',
  });
});

test('missing fields give no links', () => {
  assert.deepEqual(eventLinks({}), { trace: null, checkpoint: null });
  assert.deepEqual(eventLinks({ neatlogs_link: null, entire_checkpoint: '' }), { trace: null, checkpoint: null });
});

test('only http(s) trace links are shown', () => {
  assert.equal(eventLinks({ neatlogs_link: 'javascript:alert(1)' }).trace, null);
  assert.equal(eventLinks({ neatlogs_link: 'http://localhost:3000/traces/x' }).trace, 'http://localhost:3000/traces/x');
});

test('a checkpoint id with shell characters is not turned into a command', () => {
  assert.equal(eventLinks({ entire_checkpoint: 'abc; rm -rf /' }).checkpoint, null);
});
