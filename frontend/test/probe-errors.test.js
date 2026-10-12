import assert from 'node:assert/strict';
import test from 'node:test';

import { plainNeatlogsError } from '../src/lib/probe-errors.js';

test('AUTH_FAILED tells the owner the key was rejected, not "did not work"', () => {
  const text = plainNeatlogsError({ ok: false, code: 'AUTH_FAILED', message: 'neatlogs probe failed: AUTH_FAILED' });
  assert.match(text, /key/i);
  assert.doesNotMatch(text, /That did not work/);
});

test('TRACE_READBACK_TIMEOUT explains the trace was accepted and is still processing', () => {
  const text = plainNeatlogsError({ ok: false, code: 'TRACE_READBACK_TIMEOUT', message: 'x' });
  assert.match(text, /process|minute|again/i);
});

test('connection failures point at the endpoint or network', () => {
  for (const code of ['BACKEND_CONNECTION_FAILED', 'BACKEND_HTTP_ERROR', 'ENDPOINT_INVALID']) {
    const text = plainNeatlogsError({ ok: false, code, message: 'x' });
    assert.match(text, /reach|address|connection/i, `${code} should mention reachability`);
  }
});

test('probe failures suggest retrying and do not blame the key', () => {
  for (const code of ['BACKEND_PROBE_UNAVAILABLE', 'PROBE_TIMEOUT']) {
    const text = plainNeatlogsError({ ok: false, code, message: 'x' });
    assert.match(text, /again/i, `${code} should suggest retrying`);
    assert.doesNotMatch(text, /key was not accepted/i);
  }
});

test('CREDENTIAL_MISSING asks for a key first', () => {
  assert.match(plainNeatlogsError({ ok: false, code: 'CREDENTIAL_MISSING', message: '' }), /key/i);
});

test('a missing code falls back to the generic plain-English translation', () => {
  const text = plainNeatlogsError({ ok: false, message: 'AuthenticationError: 401 bad api key' });
  assert.match(text, /not accepted/i);
});

test('translated text never echoes a raw key from the message', () => {
  const text = plainNeatlogsError({ ok: false, code: 'AUTH_FAILED', message: 'nlk_live_supersecret rejected' });
  assert.ok(!text.includes('nlk_live_supersecret'));
});
