# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""A collection of utility functions that are used in the charm."""

import secrets
import string


def generate_random_password(length: int) -> str:
    """Randomly generate a string intended to be used as a password.

    Args:
        length: length of the randomly generated string to be returned

    Returns:
        a string with random letters and digits of length specified
    """
    choices = string.ascii_letters + string.digits
    return "".join([secrets.choice(choices) for i in range(length)])


def compare_dictionaries(dict1: dict, dict2: dict) -> set:
    """Compare two dictionaries and return a set of keys that are different."""
    different_keys = set()

    # exiting keys with different values
    for key in dict1:
        if key in dict2 and dict1[key] != dict2[key]:
            different_keys.add(key)

    # non existent keys
    different_keys = different_keys | dict2.keys() ^ dict1.keys()

    return different_keys
