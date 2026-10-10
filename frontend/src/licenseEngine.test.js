import test from 'node:test';
import assert from 'node:assert/strict';

import {
  createInitialLicenseState,
  restoreLicense,
  runRefundScenario,
} from './licenseEngine.js';

test('clean under-ceiling refunds earn promotion after three verified runs', () => {
  let state = createInitialLicenseState();

  state = runRefundScenario(state, {
    orderId: 'ORD-1001',
    customer: 'Asha Rao',
    amount: 25,
    fault: 'none',
  }).state;
  state = runRefundScenario(state, {
    orderId: 'ORD-1002',
    customer: 'Dev Mehta',
    amount: 40,
    fault: 'none',
  }).state;
  state = runRefundScenario(state, {
    orderId: 'ORD-1003',
    customer: 'Mira Sen',
    amount: 15,
    fault: 'none',
  }).state;

  assert.equal(state.level, 3);
  assert.equal(state.quarantined, false);
  assert.equal(state.cleanRuns, 0);
});

test('quiet failure demotes to L0 and records state_mismatch evidence', () => {
  const result = runRefundScenario(createInitialLicenseState(), {
    orderId: 'ORD-1002',
    customer: 'Dev Mehta',
    amount: 40,
    fault: 'quiet_failure',
  });

  assert.equal(result.state.level, 0);
  assert.equal(result.state.quarantined, true);
  assert.equal(result.run.status, 'demoted');
  assert.equal(result.run.detection.rule, 'state_mismatch');
  assert.equal(result.run.afterRefunded - result.run.beforeRefunded, 0);
});

test('restore lifts quarantine to the selected level', () => {
  const demoted = runRefundScenario(createInitialLicenseState(), {
    orderId: 'ORD-1002',
    customer: 'Dev Mehta',
    amount: 40,
    fault: 'quiet_failure',
  }).state;

  const restored = restoreLicense(demoted, 2);

  assert.equal(restored.level, 2);
  assert.equal(restored.quarantined, false);
  assert.equal(restored.cleanRuns, 0);
});
