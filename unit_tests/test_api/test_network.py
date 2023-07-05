import pytest
import re
from unittest.mock import patch, call

from api.network import Device, LAN, convert_tenacity, mac_doublecheck


@pytest.mark.parametrize(
    "tenacity,expected_result",
    [
        (1, (1, 0.02, 0)),
        (2, (2, 0.04, 1)),
        (3, (3, 0.08, 1)),
        (4, (4, 0.16, 1)),
        (5, (5, 0.32, 2)),
        (6, (5, 0.32, 2)),
        (9999999999, (5, 0.32, 2)),
        (5.001, (5, 0.32, 2)),
        (19.999, (5, 0.32, 2)),
        (0, (1, 0.02, 0)),
        (-1, (1, 0.02, 0)),
        (-9999999999, (1, 0.02, 0)),
        (-0.001, (1, 0.02, 0)),
    ],
)
def test_convert_tenacity(tenacity, expected_result):
    result = convert_tenacity(tenacity)
    assert result == expected_result


@pytest.mark.parametrize(
    "host,repeat,mac_address_values,is_ip,expected_result",
    [
        (
            "192.168.1.1",
            4,
            ["00:00:00:00:00:00", "AA:BB:CC:DD:EE:FF", None, "00:00:00:00:00:00"],
            True,
            "AA:BB:CC:DD:EE:FF",
        ),
        (
            "192.168.1.1",
            4,
            ["00:00:00:00:00:00", None, "00:00:00:00:00:00", None],
            True,
            None,
        ),
        ("192.168.1.1", 1, ["AA:BB:CC:DD:EE:FF"], True, "AA:BB:CC:DD:EE:FF"),
        (
            "hostname",
            4,
            ["00:00:00:00:00:00", "AA:BB:CC:DD:EE:FF", None, "00:00:00:00:00:00"],
            False,
            "AA:BB:CC:DD:EE:FF",
        ),
        ("hostname", 2, ["00:00:00:00:00:00", None], False, None),
        ("hostname", 1, ["AA:BB:CC:DD:EE:FF"], False, "AA:BB:CC:DD:EE:FF"),
    ],
)
@patch("api.network.get_mac_address")
@patch("api.network.time.sleep")
def test_mac_doublecheck(
    mock_sleep,
    mock_get_mac,
    host,
    repeat,
    mac_address_values,
    is_ip,
    expected_result,
):
    # Set the return value for get_mac_address
    mock_get_mac.side_effect = mac_address_values

    # Call the function
    result = mac_doublecheck(host, repeat, 1)

    # Check if the correct keyword argument was present in each call to get_mac_address
    key = "ip" if is_ip else "hostname"
    for call in mock_get_mac.call_args_list:
        assert key in call[1] and call[1][key] == host

    # Assert that sleep was called with the correct argument
    for call in mock_sleep.call_args_list:
        assert call[0] == (1,)

    # Assert the correct MAC was returned
    assert result == expected_result
