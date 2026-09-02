"""The matcher follows Salt's grain-matching semantics."""
import pytest

from api.utils.matching import glob_match, list_match, subdict_match

GRAINS = {
    "os": "Ubuntu",
    "osrelease": "24.04",
    "kernelrelease": "6.8.0-41-generic",
    "virtual": "kvm",
    "num_cpus": 8,
    "systemd": {"version": "255"},
    "ec2_tags": {"environment": "production", "role": "web"},
    "ipv4": ["127.0.0.1", "10.0.3.14"],
    "disks": [{"name": "sda"}, {"name": "sdb"}],
    "selinux": {"enabled": False},
}


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("os:Ubuntu", True),
        ("os:ubuntu", False),          # Salt's grain matching is case sensitive
        ("os:Ubunt*", True),           # globs
        ("os:Debian", False),
        ("ec2_tags:environment:production", True),   # nested
        ("ec2_tags:environment:staging", False),
        ("ec2_tags:role:w*", True),
        ("systemd:version:255", True),
        ("num_cpus:8", True),          # non-string values
        ("selinux:enabled:False", True),
        ("selinux:enabled:True", False),
        ("ipv4:10.0.3.14", True),      # a list value matches on any element
        ("ipv4:10.0.*", True),
        ("ipv4:192.168.1.1", False),
        ("disks:name:sdb", True),      # list of dicts
        ("kernelrelease:6.8.0-41-generic", True),
        ("os", True),                  # bare key means "present"
        ("nosuchgrain", False),
        ("nosuchgrain:value", False),
        ("", False),
    ],
)
def test_subdict_match(expression, expected):
    assert subdict_match(GRAINS, expression) is expected


def test_a_value_containing_the_delimiter_still_matches():
    # The delimiter appears in both the key path and the value, so every split
    # point has to be tried.
    data = {"url": "http://example.test:8080"}
    assert subdict_match(data, "url:http://example.test:8080") is True


def test_glob_and_list_matching():
    assert glob_match("web01.example.test", "web*") is True
    assert glob_match("db01.example.test", "web*") is False
    assert list_match("web01", "web01,web02") is True
    assert list_match("web03", "web01,web02") is False
