/** Names for action classes, and the MCP tool rules of the policy editor. */

const SERVER_NAMES = {
  github: 'GitHub', gitlab: 'GitLab', aws: 'AWS', gcp: 'GCP', postgres: 'Postgres', mysql: 'MySQL',
  sqlite: 'SQLite', supabase: 'Supabase', vercel: 'Vercel', jira: 'Jira', slack: 'Slack', linear: 'Linear',
  notion: 'Notion', sentry: 'Sentry', figma: 'Figma',
};
const RISKS = ['read', 'write', 'destructive'];

export const isMcpClass = (key) => String(key || '').startsWith('mcp:');

/** "mcp:github" -> "GitHub (MCP)"; built-in classes keep their key. */
export function classLabel(key) {
  if (!isMcpClass(key)) return String(key || '');
  const server = key.slice(4).split(/[-_.\s]+/).filter(Boolean)
    .map((w) => SERVER_NAMES[w.toLowerCase()] || w[0].toUpperCase() + w.slice(1)).join(' ');
  return `${server} (MCP)`;
}

/** "mcp__github__* write" per line -> { "mcp__github__*": { risk: "write" } }. Throws on a bad line. */
export function parseToolRules(text) {
  const rules = {};
  for (const line of String(text || '').split('\n').map((s) => s.trim()).filter(Boolean)) {
    const [pattern, ...words] = line.split(/\s+/);
    const rule = {};
    for (const word of words) {
      const ceiling = word.match(/^(?:ceiling|max)=([012])$/);
      if (RISKS.includes(word)) rule.risk = word;
      else if (word === 'forbidden') rule.forbidden = true;
      else if (ceiling) rule.ceiling = Number(ceiling[1]);
      else throw new Error(`Tool rule "${line}": unknown "${word}" (use read, write, destructive, forbidden or ceiling=0..2).`);
    }
    if (!Object.keys(rule).length) throw new Error(`Tool rule "${line}" needs a risk, forbidden or ceiling=0..2.`);
    rules[pattern] = rule;
  }
  return rules;
}

export function formatToolRules(rules) {
  return Object.entries(rules || {}).map(([pattern, r]) => [
    pattern, r.risk, r.forbidden ? 'forbidden' : '', r.ceiling != null ? `ceiling=${r.ceiling}` : '',
  ].filter(Boolean).join(' ')).join('\n');
}
