import assert from 'node:assert/strict';
import test from 'node:test';

import { classLabel, formatToolRules, isMcpClass, parseToolRules } from '../src/lib/action-classes.js';

test('MCP classes read as their server', () => {
  assert.equal(classLabel('mcp:github'), 'GitHub (MCP)');
  assert.equal(classLabel('mcp:linear-tasks'), 'Linear Tasks (MCP)');
  assert.equal(classLabel('mcp:aws'), 'AWS (MCP)');
  assert.equal(classLabel('file-edit'), 'file-edit');
  assert.equal(classLabel(''), '');
  assert.equal(isMcpClass('mcp:github'), true);
  assert.equal(isMcpClass('git-remote'), false);
});

test('tool rules are one line each: glob, then risk / forbidden / ceiling', () => {
  const rules = parseToolRules('mcp__github__* write\n\n  mcp__aws__* forbidden \nmcp__github__merge_* destructive ceiling=1');
  assert.deepEqual(rules, {
    'mcp__github__*': { risk: 'write' },
    'mcp__aws__*': { forbidden: true },
    'mcp__github__merge_*': { risk: 'destructive', ceiling: 1 },
  });
  assert.equal(formatToolRules(rules), 'mcp__github__* write\nmcp__aws__* forbidden\nmcp__github__merge_* destructive ceiling=1');
  assert.equal(formatToolRules(null), '');
});

test('a tool rule that says nothing, or something unknown, is refused', () => {
  assert.throws(() => parseToolRules('mcp__github__*'), /mcp__github__\*/);
  assert.throws(() => parseToolRules('mcp__github__* risky'), /risky/);
  assert.throws(() => parseToolRules('mcp__github__* ceiling=5'), /ceiling=5/);
});
