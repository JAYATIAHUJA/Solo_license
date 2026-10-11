/** Turn a raw connection error into something a shop owner can act on.
 *  Pure module (no React, no CSS imports) so it is unit-testable in node. */

export function plainError(message = '') {
  const m = String(message);
  if (/401|403|unauthori[sz]ed|forbidden|invalid.*key|api.?key|permission|credential/i.test(m)) return 'That key was not accepted. Check you copied all of it and try again.';
  if (/429|quota|rate.?limit|exhausted/i.test(m)) return 'The service says you have hit a usage limit. Try again later or check your plan.';
  if (/404|not.?found|model/i.test(m)) return 'The service did not recognise that model name.';
  if (/timeout|timed out|connect|resolve|network|unreachable|ssl/i.test(m)) return 'Could not reach the service. Check the address and your internet connection.';
  if (/add .*first|https:\/\//i.test(m)) return m;
  return 'That did not work. Check the details and try again.';
}
