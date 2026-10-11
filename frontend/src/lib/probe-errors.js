/** Plain-English guidance for the neatlogs Doctor probe result.
 *
 * The backend returns a structured code (`AUTH_FAILED`,
 * `TRACE_READBACK_TIMEOUT`, …) alongside its message; these translations turn
 * each code into something a shop owner can act on, instead of the generic
 * "That did not work." Translations never echo the raw key. */

import { plainError } from './plain-errors.js';

const PROBE_TEXT = {
  AUTH_FAILED: 'neatlogs did not accept that key. Copy the whole key from your neatlogs account and try again.',
  CREDENTIAL_MISSING: 'Add a neatlogs API key first.',
  TRACE_READBACK_TIMEOUT: 'neatlogs accepted the trace but is still processing it. Try again in a minute.',
  BACKEND_CONNECTION_FAILED: 'Could not reach neatlogs. Check the service address and your internet connection.',
  BACKEND_HTTP_ERROR: 'neatlogs answered with an error. Check the service address, or neatlogs status, and try again.',
  ENDPOINT_INVALID: 'That neatlogs service address is not valid. Keep the standard address unless neatlogs told you otherwise.',
  BACKEND_PROBE_UNAVAILABLE: 'The diagnostic could not finish - that does not mean your key is wrong. Try again in a moment.',
  PROBE_TIMEOUT: 'The diagnostic did not finish in time - neatlogs may be busy. Try again in a minute.',
};

/** Translate a structured probe result into guidance for the Test row. */
export function plainNeatlogsError(result = {}) {
  const code = String(result.code || '');
  if (PROBE_TEXT[code]) return PROBE_TEXT[code];
  // No structured code (raw network error, older API): fall back to the
  // generic provider-error translation of the raw message.
  return plainError(result.message);
}
