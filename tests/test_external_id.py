import pytest

from xacct.external_id import generate, validate


def test_generated_ids_are_valid_and_the_right_length():
    for length in (32, 48, 100):
        value = generate(length)
        assert len(value) == length
        assert validate(value) == value


def test_generated_ids_are_different_each_time():
    assert len({generate() for _ in range(50)}) == 50


@pytest.mark.parametrize("length", [10, 31, 2000])
def test_generate_refuses_bad_lengths(length):
    with pytest.raises(ValueError):
        generate(length)


@pytest.mark.parametrize(
    "value, message",
    [
        ("", "empty"),
        ("short-id", "32-1224"),
        ("x" * 1225, "32-1224"),
        ("has spaces in it but is long enough 12345", "may only contain"),
        ("semicolon;is-not-allowed-0123456789abcdef", "may only contain"),
    ],
)
def test_validate_rejects_bad_values(value, message):
    with pytest.raises(ValueError, match=message):
        validate(value)


def test_validate_accepts_all_aws_allowed_symbols():
    value = "abcXYZ019_+=,.@:/-" + "a" * 20
    assert validate(value) == value
