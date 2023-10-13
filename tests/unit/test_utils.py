#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import re

from utils import compare_dictionaries, generate_random_hash, generate_random_password


def test_generate_random_hash():
    """Test generate_random_hash function."""
    random_hash = generate_random_hash()
    assert len(random_hash) == 32
    assert re.match(r"^[a-f0-9]{32}$", random_hash)


def test_generate_random_password():
    """Test generate_random_password function."""
    random_password = generate_random_password(20)
    assert len(random_password) == 20
    assert re.match(r"^[a-zA-Z0-9]{20}$", random_password)


def test_compare_dictionaries():
    dict1 = {"a": 1, "b": 2, "c": 3, "f": 4}
    dict2 = {"a": 1, "b": 3, "d": 5, "e": 6, "f": 4}

    assert compare_dictionaries(dict1, dict2) == {"b", "c", "d", "e"}
