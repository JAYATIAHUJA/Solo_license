from sololicense.api.app import make_idempotency_key


def test_make_idempotency_key_is_stable_and_namespaced():
    first = make_idempotency_key("intake", "hello", "ORD-1001", 25.0)
    second = make_idempotency_key("intake", "hello", "ORD-1001", 25.0)
    other = make_idempotency_key("manual", "hello", "ORD-1001", 25.0)

    assert first == second
    assert first != other
    assert first.startswith("intake:")
