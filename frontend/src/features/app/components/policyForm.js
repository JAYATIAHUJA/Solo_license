/** Pure policy-draft helpers. Keeping validation outside React makes it easy
 * to test and prevents the editor from emitting malformed rule payloads. */

const numeric = (value) => Number(String(value ?? '').trim());

function stringRule(rule = {}) {
  return {
    task_class: rule.task_class || '',
    allowed_tool: rule.allowed_tool || rule.task_class || '',
    requires_approval_at_or_above: String(rule.requires_approval_at_or_above ?? 2),
    l2_ceiling: String(rule.l2_ceiling ?? 0),
    evaluation_window: String(rule.evaluation_window ?? 3),
    minimum_samples: String(rule.minimum_samples ?? 3),
    minimum_verified_pass_rate: String(rule.minimum_verified_pass_rate ?? 1),
  };
}

export function draftFromPolicy(policy = {}) {
  return {
    name: policy.name || '',
    summary: policy.summary || '',
    rules: Object.fromEntries((policy.rules || []).map((rule) => [
      rule.task_class, stringRule(rule),
    ])),
  };
}

export function validatePolicyDraft(draft, taskClasses = []) {
  const errors = [];
  if (!String(draft?.name || '').trim()) errors.push('Give this policy a name.');
  for (const taskClass of taskClasses) {
    const rule = draft?.rules?.[taskClass.key];
    if (!rule) {
      errors.push(`${taskClass.label || taskClass.key} needs a rule.`);
      continue;
    }
    if (String(rule.allowed_tool || '').trim() !== taskClass.key) {
      errors.push(`${taskClass.label || taskClass.key} must use its registered tool.`);
    }
    const approval = numeric(rule.requires_approval_at_or_above);
    const ceiling = numeric(rule.l2_ceiling);
    const window = numeric(rule.evaluation_window);
    const samples = numeric(rule.minimum_samples);
    const passRate = numeric(rule.minimum_verified_pass_rate);
    if (!Number.isInteger(approval) || approval < 0 || approval > 3) {
      errors.push(`${taskClass.label || taskClass.key}: approval level must be from 0 to 3.`);
    }
    if (!Number.isFinite(ceiling) || ceiling < 0) {
      errors.push(`${taskClass.label || taskClass.key}: the L2 ceiling must be zero or more.`);
    }
    if (!Number.isInteger(window) || window < 1) {
      errors.push(`${taskClass.label || taskClass.key}: evaluation window must be at least 1.`);
    }
    if (!Number.isInteger(samples) || samples < 1) {
      errors.push(`${taskClass.label || taskClass.key}: minimum samples must be at least 1.`);
    } else if (Number.isInteger(window) && samples > window) {
      errors.push(`${taskClass.label || taskClass.key}: minimum samples cannot exceed the evaluation window.`);
    }
    if (!Number.isFinite(passRate) || passRate < 0 || passRate > 1) {
      errors.push(`${taskClass.label || taskClass.key}: verified pass rate must be between 0 and 1.`);
    }
  }
  return errors;
}

export function policyPayload(draft, taskClasses = []) {
  return {
    name: String(draft.name || '').trim(),
    summary: String(draft.summary || '').trim(),
    rules: taskClasses.map((taskClass) => {
      const rule = draft.rules[taskClass.key];
      return {
        task_class: taskClass.key,
        allowed_tool: String(rule.allowed_tool || '').trim(),
        requires_approval_at_or_above: numeric(rule.requires_approval_at_or_above),
        l2_ceiling: numeric(rule.l2_ceiling),
        evaluation_window: numeric(rule.evaluation_window),
        minimum_samples: numeric(rule.minimum_samples),
        minimum_verified_pass_rate: numeric(rule.minimum_verified_pass_rate),
      };
    }),
  };
}
