"""Tests for extract_form_field_info.py choice-field normalization.

Regression guard for the /_States_ scalar decoding bug: when /_States_ is a
list of strings (rather than [value, text] pairs), the previous code sliced
each string by character (state[0], state[1]) and produced garbage like
{"value": "O", "text": "n"} for the option "One".
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import extract_form_field_info as effi


def test_choice_options_from_scalar_strings():
    """Each scalar string becomes both value and text."""
    states = ["One", "Two", "Three"]
    result = effi._choice_options_from_states(states)
    assert result == [
        {"value": "One", "text": "One"},
        {"value": "Two", "text": "Two"},
        {"value": "Three", "text": "Three"},
    ]


def test_choice_options_from_value_text_pairs():
    """2-element sequences are unpacked as (value, text)."""
    states = [["1", "One"], ["2", "Two"]]
    result = effi._choice_options_from_states(states)
    assert result == [
        {"value": "1", "text": "One"},
        {"value": "2", "text": "Two"},
    ]


def test_choice_options_from_empty_states():
    """Empty /_States_ yields an empty option list."""
    assert effi._choice_options_from_states([]) == []


def test_choice_options_from_tuple_pairs():
    """Tuples are treated the same as lists for the pair path."""
    states = [("1", "One"), ("2", "Two")]
    result = effi._choice_options_from_states(states)
    assert result == [
        {"value": "1", "text": "One"},
        {"value": "2", "text": "Two"},
    ]


def test_make_field_dict_choice_with_scalar_states():
    """End-to-end: a choice field with scalar /_States_ produces correct options."""
    field = {"/FT": "/Ch", "/_States_": ["A", "B", "C"]}
    result = effi.make_field_dict(field, "my_field")
    assert result["type"] == "choice"
    assert result["choice_options"] == [
        {"value": "A", "text": "A"},
        {"value": "B", "text": "B"},
        {"value": "C", "text": "C"},
    ]
