"""攻击数字核对(宪法第四条)。"""

from __future__ import annotations

from mail2leads.verify.numbers import unverified_numbers


def test_number_absent_from_source_is_flagged():
    assert unverified_numbers(["500", "A-12", "3000"], "Please quote 500 units of model A-12.") == (
        "3000",
    )


def test_thousands_separator_is_not_a_hallucination():
    assert unverified_numbers(["1000"], "We need 1,000 pcs before Dec 15.") == ()


def test_chinese_comma_and_whitespace_normalized():
    assert unverified_numbers(["2000"], "数量:2,000 件") == ()


def test_clean_summary_passes():
    assert (
        unverified_numbers(
            ["20", "2026-11-30"], "Need 20 tons, CIF Hamburg, delivery by 2026-11-30."
        )
        == ()
    )


def test_empty_quote_is_ignored():
    assert unverified_numbers(["", "48"], "48 units") == ()


def test_numeric_substrings_and_whitespace_do_not_pass_verification():
    assert unverified_numbers(["32", "1000"], "We need 132 units; reference 10 00 only.") == (
        "32",
        "1000",
    )
