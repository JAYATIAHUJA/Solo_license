"""Policy lifecycle and scoped autonomy-evidence evaluation."""

from __future__ import annotations

import sqlite3

from sololicense.config import Config
from sololicense.db.repositories import policies as policy_repo
from sololicense.domain.policy import EvaluationProgress, PolicyImpact, PolicyRule, PolicyVersion, evaluate_runs
from sololicense.domain.task_classes import TASK_CLASSES
from sololicense.security import Actor


class PolicyService:
    def __init__(self, conn: sqlite3.Connection, config: Config) -> None:
        self._conn = conn
        self._config = config

    def ensure_default_policy(self) -> PolicyVersion:
        active = policy_repo.active_policy(self._conn)
        if active is not None:
            return active
        rules = tuple(
            PolicyRule(
                task_class=key, allowed_tool=key, requires_approval_at_or_above=2,
                l2_ceiling=self._config.ceiling_for(key),
                evaluation_window=self._config.promotion_clean_runs,
                minimum_samples=self._config.promotion_clean_runs,
                minimum_verified_pass_rate=1.0,
            )
            for key in TASK_CLASSES
        )
        policy = policy_repo.create_version(
            self._conn, name="Default safety policy", summary="Migrated from workspace safety settings.",
            rules=rules, created_by="system:policy-migration",
        )
        # The first policy deliberately reproduces the pre-policy workspace
        # configuration. Historical runs therefore belong to v1 for audit and
        # its evidence window, while later versions always begin fresh.
        self._conn.execute(
            "UPDATE runs SET policy_version = ? WHERE policy_version IS NULL",
            (policy.version,),
        )
        self._conn.commit()
        return policy

    def active(self) -> PolicyVersion:
        return self.ensure_default_policy()

    def get(self, version: int) -> PolicyVersion:
        policy = policy_repo.get_policy(self._conn, version)
        if policy is None:
            raise KeyError(f"Unknown policy version {version}.")
        return policy

    def evaluation_for(self, task_class: str, *, policy: PolicyVersion | None = None) -> EvaluationProgress:
        active = policy or self.active()
        rule = active.rule_for(task_class)
        rows = self._conn.execute(
            """
            SELECT status FROM runs
             WHERE task_class = ? AND policy_version = ? AND executed = 1
             ORDER BY id DESC LIMIT ?
            """,
            (task_class, active.version, rule.evaluation_window),
        ).fetchall()
        return evaluate_runs(
            [row["status"] == "clean" for row in rows], rule, policy_version=active.version
        )

    def preview_activation(self, rules: tuple[PolicyRule, ...]) -> list[PolicyImpact]:
        current = self.active()
        _validate_complete_rules(rules)
        next_version = current.version + 1
        impacts: list[PolicyImpact] = []
        for rule in rules:
            progress = self._evaluation(rule, next_version)
            if progress.eligible:
                action = "eligible"
                reason = "Existing evidence under this policy version meets the promotion rule."
            else:
                action = "hold_for_review"
                reason = (
                    f"Needs {progress.required_samples} verified runs under policy v{next_version}; "
                    f"0 are available."
                )
            impacts.append(PolicyImpact(rule.task_class, current.version, next_version, progress, action, reason))
        return impacts

    def activate(
        self, *, name: str, summary: str, rules: tuple[PolicyRule, ...], actor: Actor
    ) -> PolicyVersion:
        if not name.strip():
            raise ValueError("policy name is required")
        _validate_complete_rules(rules)
        impacts = self.preview_activation(rules)
        try:
            self._conn.execute("BEGIN")
            policy_repo.supersede_active(self._conn)
            policy = policy_repo.create_version(
                self._conn, name=name.strip(), summary=summary.strip(), rules=rules,
                created_by=actor.actor_id,
            )
            policy_repo.insert_impacts(self._conn, impacts)
            self._conn.commit()
            return policy
        except Exception:
            self._conn.rollback()
            raise

    def _evaluation(self, rule: PolicyRule, version: int) -> EvaluationProgress:
        rows = self._conn.execute(
            """
            SELECT status FROM runs
             WHERE task_class = ? AND policy_version = ? AND executed = 1
             ORDER BY id DESC LIMIT ?
            """,
            (rule.task_class, version, rule.evaluation_window),
        ).fetchall()
        return evaluate_runs([row["status"] == "clean" for row in rows], rule, policy_version=version)


def _validate_complete_rules(rules: tuple[PolicyRule, ...]) -> None:
    keys = {rule.task_class for rule in rules}
    if keys != set(TASK_CLASSES):
        raise ValueError("Policy must define exactly one rule for every task class.")
    if len(keys) != len(rules):
        raise ValueError("Policy has duplicate task class rules.")
    for rule in rules:
        if rule.allowed_tool != rule.task_class:
            raise ValueError("Policy tool must match its registered task class.")
