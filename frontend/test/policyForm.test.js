import assert from 'node:assert/strict';
import test from 'node:test';

import {
  draftFromPolicy, policyPayload, validatePolicyDraft,
} from '../src/features/app/components/policyForm.js';

const taskClasses = [
  { key: 'refund', label: 'Refunds' },
  { key: 'store_credit', label: 'Store credit' },
];

const policy = {
  name: 'Default safety policy',
  summary: 'Safe defaults.',
  rules: [
    { task_class: 'refund', allowed_tool: 'refund', requires_approval_at_or_above: 1, l2_ceiling: 50, evaluation_window: 3, minimum_samples: 3, minimum_verified_pass_rate: 1 },
    { task_class: 'store_credit', allowed_tool: 'store_credit', requires_approval_at_or_above: 1, l2_ceiling: 75, evaluation_window: 3, minimum_samples: 3, minimum_verified_pass_rate: 1 },
  ],
};

test('policy payload preserves a changed refund ceiling and every task class', () => {
  const draft = draftFromPolicy(policy);
  draft.rules.refund.l2_ceiling = '25';

  assert.deepEqual(validatePolicyDraft(draft, taskClasses), []);
  const payload = policyPayload(draft, taskClasses);
  assert.equal(payload.rules.find((rule) => rule.task_class === 'refund').l2_ceiling, 25);
  assert.deepEqual(payload.rules.map((rule) => rule.task_class).sort(), ['refund', 'store_credit']);
});

test('policy validation rejects a missing rule and an impossible evidence threshold', () => {
  const draft = draftFromPolicy(policy);
  delete draft.rules.store_credit;
  draft.rules.refund.minimum_samples = '4';
  draft.rules.refund.evaluation_window = '3';

  const errors = validatePolicyDraft(draft, taskClasses);
  assert.ok(errors.some((error) => error.includes('Store credit')));
  assert.ok(errors.some((error) => error.includes('cannot exceed')));
});
