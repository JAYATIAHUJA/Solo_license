import assert from 'node:assert/strict';
import test from 'node:test';

import { apiUrl } from '../src/lib/api-base.js';

test('apiUrl keeps relative requests for the local Vite proxy', () => {
  assert.equal(apiUrl('/api/session', ''), '/api/session');
});

test('apiUrl prefixes a deployed API origin without a double slash', () => {
  assert.equal(
    apiUrl('/api/session', 'https://solo-license-api.vercel.app/'),
    'https://solo-license-api.vercel.app/api/session',
  );
});
