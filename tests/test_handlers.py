import hashlib
from handlers.handlers import anonymize_user


def test_anonymize_user_consistency():
    """Ověření, že hashování je stabilní a deterministické."""
    user_id = 123456789
    hash1 = anonymize_user(user_id)
    hash2 = anonymize_user(user_id)

    assert hash1 == hash2
    # Hash nesmí obsahovat původní ID.
    assert str(user_id) not in hash1
    assert len(hash1) == 64