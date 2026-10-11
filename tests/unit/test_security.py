from sololicense.security import Role, TokenAuthenticator


def test_token_authenticator_returns_the_configured_actor_and_role():
    authenticator = TokenAuthenticator.from_json(
        '{"operator-token":{"id":"ops-17","role":"operator"},'
        '"admin-token":{"id":"admin-1","role":"admin"}}'
    )

    actor = authenticator.authenticate("operator-token")

    assert actor.actor_id == "ops-17"
    assert actor.role is Role.OPERATOR


def test_token_authenticator_rejects_unknown_or_malformed_tokens():
    authenticator = TokenAuthenticator.from_json(
        '{"approver-token":{"id":"ap-9","role":"approver"}}'
    )

    assert authenticator.authenticate("wrong-token") is None
