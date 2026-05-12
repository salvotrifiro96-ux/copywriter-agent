import json

import pytest

from agent.common import clean_list, clean_str, extract_json, section


class TestExtractJson:
    def test_plain_array(self):
        assert extract_json('[{"a": 1}]') == [{"a": 1}]

    def test_plain_object(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_strips_json_fence(self):
        raw = '```json\n[{"a": 1}]\n```'
        assert extract_json(raw) == [{"a": 1}]

    def test_strips_bare_fence(self):
        raw = '```\n{"a": 1}\n```'
        assert extract_json(raw) == {"a": 1}

    def test_invalid_raises(self):
        with pytest.raises(json.JSONDecodeError):
            extract_json("not json")


class TestSection:
    def test_empty_body_returns_empty(self):
        assert section("Label", "") == ""
        assert section("Label", "   ") == ""
        assert section("Label", None) == ""  # type: ignore[arg-type]

    def test_renders_label_and_body(self):
        out = section("Target", "imprenditori 35-55")
        assert "## Target" in out
        assert "imprenditori 35-55" in out


class TestCleanStr:
    @pytest.mark.parametrize("value,expected", [
        (None, ""),
        ("", ""),
        ("  hello  ", "hello"),
        (42, "42"),
    ])
    def test_clean_str(self, value, expected):
        assert clean_str(value) == expected


class TestCleanList:
    def test_none_returns_empty(self):
        assert clean_list(None) == ()

    def test_single_string_wrapped(self):
        assert clean_list("hashtag") == ("hashtag",)

    def test_empty_string_not_wrapped(self):
        assert clean_list("") == ()
        assert clean_list("   ") == ()

    def test_list_filters_blanks(self):
        assert clean_list(["a", "", "  ", "b"]) == ("a", "b")

    def test_mixed_types(self):
        assert clean_list([1, 2, "x"]) == ("1", "2", "x")

    def test_unsupported_type_returns_empty(self):
        assert clean_list(42) == ()
        assert clean_list({"a": 1}) == ()
