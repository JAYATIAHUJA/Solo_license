"""Authentication primitives for the HTTP boundary.

Tokens remain deployment secrets. The rest of the application receives only
the authenticated actor identity and role it may safely record in audit data.
"""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    OPERATOR = "operator"
    APPROVER = "approver"
    ADMIN = "admin"


@dataclass(frozen=True)
class Actor:
    actor_id: str
    role: Role


class TokenAuthenticator:
    """Authenticate bearer tokens configured outside application storage."""

    def __init__(self, actors_by_token: dict[str, Actor]) -> None:
        self._actors_by_token = actors_by_token

    @classmethod
    def from_json(cls, value: str) -> "TokenAuthenticator":
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("SOLO_API_TOKENS must be valid JSON.") from error
        if not isinstance(raw, dict) or not raw:
            raise ValueError("SOLO_API_TOKENS must define at least one token.")

        actors: dict[str, Actor] = {}
        for token, details in raw.items():
            if not isinstance(token, str) or not token.strip() or not isinstance(details, dict):
                raise ValueError("Each API token must have an id and role.")
            actor_id = details.get("id")
            role = details.get("role")
            if not isinstance(actor_id, str) or not actor_id.strip():
                raise ValueError("Each API token must have a non-empty id.")
            try:
                actors[token] = Actor(actor_id=actor_id.strip(), role=Role(role))
            except ValueError as error:
                raise ValueError("Each API token role must be operator, approver, or admin.") from error
        return cls(actors)

    def authenticate(self, token: str) -> Actor | None:
        for configured_token, actor in self._actors_by_token.items():
            if hmac.compare_digest(configured_token, token):
                return actor
        return None


def permits(actor: Actor, required: Role) -> bool:
    """Return whether an actor's role includes the requested capability."""
    rank = {Role.OPERATOR: 0, Role.APPROVER: 1, Role.ADMIN: 2}
    return rank[actor.role] >= rank[required]
