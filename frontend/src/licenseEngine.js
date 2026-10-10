export const LICENSE_LEVELS = [
  { level: 0, name: 'L0', label: 'Suggest only' },
  { level: 1, name: 'L1', label: 'Draft + approve' },
  { level: 2, name: 'L2', label: 'Auto under ceiling' },
  { level: 3, name: 'L3', label: 'Full auto, audited' },
];

export const ORDERS = [
  { orderId: 'ORD-1001', customer: 'Asha Rao', amount: 25 },
  { orderId: 'ORD-1002', customer: 'Dev Mehta', amount: 40 },
  { orderId: 'ORD-1003', customer: 'Mira Sen', amount: 15 },
  { orderId: 'ORD-1004', customer: 'Nolan Price', amount: 120 },
];

const PROMOTION_CLEAN_RUNS = 3;
const L2_AUTO_REFUND_CEILING = 50;

export function createInitialLicenseState() {
  return {
    level: 2,
    cleanRuns: 0,
    quarantined: false,
    demotedFrom: null,
    nextRunId: 1,
    refundedByOrder: Object.fromEntries(ORDERS.map((order) => [order.orderId, 0])),
    history: [
      {
        sha: '484faf5',
        kind: 'restore',
        from: 0,
        to: 2,
        reason: 'Human reviewed evidence and restored refund class',
      },
    ],
  };
}

export function restoreLicense(state, targetLevel) {
  return {
    ...state,
    level: targetLevel,
    cleanRuns: 0,
    quarantined: false,
    demotedFrom: null,
    history: [
      {
        sha: shortSha(state.nextRunId + 71),
        kind: 'restore',
        from: state.level,
        to: targetLevel,
        reason: 'Human restored after evidence review',
      },
      ...state.history,
    ],
  };
}

export function runRefundScenario(state, order) {
  const effectiveLevel = state.quarantined ? 0 : state.level;
  const policyAllowsAuto =
    effectiveLevel >= 3 ||
    (effectiveLevel >= 2 && order.amount <= L2_AUTO_REFUND_CEILING);
  const fault = order.fault ?? 'none';
  const attemptedAuto = fault === 'policy_violation' || policyAllowsAuto;
  const beforeRefunded = state.refundedByOrder[order.orderId] ?? 0;
  const actualDelta = attemptedAuto && fault !== 'quiet_failure' ? order.amount : 0;
  const afterRefunded = beforeRefunded + actualDelta;
  const detection = detect({
    attemptedAuto,
    policyAllowsAuto,
    intendedDelta: attemptedAuto ? order.amount : 0,
    actualDelta,
    fault,
  });
  const baseRun = {
    id: state.nextRunId,
    orderId: order.orderId,
    customer: order.customer,
    amount: order.amount,
    beforeRefunded,
    afterRefunded,
    intendedDelta: attemptedAuto ? order.amount : 0,
    authorized: policyAllowsAuto ? 'AUTO_EXECUTE' : 'SUGGEST_ONLY',
    fault,
    traceId: `tr_${shortSha(state.nextRunId + 11)}`,
    detection,
    status: detection ? 'demoted' : attemptedAuto ? 'clean' : 'suggested',
  };

  const refundedByOrder = {
    ...state.refundedByOrder,
    [order.orderId]: afterRefunded,
  };

  if (detection) {
    return {
      run: baseRun,
      state: {
        ...state,
        level: 0,
        cleanRuns: 0,
        quarantined: true,
        demotedFrom: state.level,
        nextRunId: state.nextRunId + 1,
        refundedByOrder,
        history: [
          {
            sha: shortSha(state.nextRunId + 43),
            kind: 'demote',
            from: state.level,
            to: 0,
            reason: `${detection.rule} fired on run #${state.nextRunId}`,
          },
          ...state.history,
        ],
      },
    };
  }

  const cleanRuns = attemptedAuto ? state.cleanRuns + 1 : state.cleanRuns;
  const shouldPromote =
    !state.quarantined && attemptedAuto && cleanRuns >= PROMOTION_CLEAN_RUNS && state.level < 3;
  const nextLevel = shouldPromote ? state.level + 1 : state.level;

  return {
    run: baseRun,
    state: {
      ...state,
      level: nextLevel,
      cleanRuns: shouldPromote ? 0 : cleanRuns,
      nextRunId: state.nextRunId + 1,
      refundedByOrder,
      history: shouldPromote
        ? [
            {
              sha: shortSha(state.nextRunId + 29),
              kind: 'promote',
              from: state.level,
              to: nextLevel,
              reason: `${PROMOTION_CLEAN_RUNS} consecutive verified-clean runs`,
            },
            ...state.history,
          ]
        : state.history,
    },
  };
}

function detect({ attemptedAuto, policyAllowsAuto, intendedDelta, actualDelta, fault }) {
  if (attemptedAuto && !policyAllowsAuto) {
    return {
      rule: 'policy_breach',
      severity: 'critical',
      message: 'The agent attempted execution beyond the current license.',
    };
  }

  if (fault === 'missing_verification') {
    return {
      rule: 'missing_verification',
      severity: 'high',
      message: 'Execution completed without reading SQLite back.',
    };
  }

  if (attemptedAuto && intendedDelta !== actualDelta) {
    return {
      rule: 'state_mismatch',
      severity: 'critical',
      message: `Intended $${intendedDelta.toFixed(2)}, SQLite moved $${actualDelta.toFixed(2)}.`,
    };
  }

  return null;
}

function shortSha(seed) {
  return Math.abs(Math.imul(seed, 2654435761)).toString(16).slice(0, 7).padStart(7, '0');
}
