from __future__ import annotations

import pytest

from raiw_api.errors import APIError
from raiw_api.services import parse_regions


def test_parse_regions_accepts_lists_and_objects():
    assert parse_regions("[[1,2,3,4]]", width=20, height=20) == [(1, 2, 3, 4)]
    assert parse_regions('[{"x":1,"y":2,"width":3,"height":4}]', width=20, height=20) == [(1, 2, 3, 4)]


def test_parse_regions_rejects_out_of_bounds():
    with pytest.raises(APIError) as exc:
        parse_regions("[[19,19,2,2]]", width=20, height=20)
    assert exc.value.code == "invalid_regions"
