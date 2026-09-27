import pytest

from aimail.config import parse_mailbox_access


def test_parse_multiple_employee_mailbox_access():
    grants = parse_mailbox_access(
        '{"larry@glocalstorage.com":["sales@glocalstorage.com",'
        '"larry@glocalstorage.com"],'
        '"isaac@semifly.ai":["sales@glocalstorage.com",'
        '"isaac@semifly.ai"]}'
    )
    assert grants == {
        "larry@glocalstorage.com": (
            "sales@glocalstorage.com",
            "larry@glocalstorage.com",
        ),
        "isaac@semifly.ai": ("sales@glocalstorage.com", "isaac@semifly.ai"),
    }


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        '"bad"',
        '{"no-email": ["sales@example.test"]}',
        '{"a@example.test": "sales@example.test"}',
        '{"a@example.test": [1]}',
        '{"a@example.test": ["not-an-email"]}',
        '{"A@example.test": ["one@example.test"],"a@example.test": ["two@example.test"]}',
    ],
)
def test_parse_mailbox_access_rejects_invalid_shapes(raw):
    with pytest.raises(RuntimeError, match="MAILBOX_ACCESS"):
        parse_mailbox_access(raw)
