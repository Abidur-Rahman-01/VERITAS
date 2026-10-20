from netaddr.cidr import is_ip_in_network

def test_inside_subnet():
    assert is_ip_in_network('192.168.1.5', '192.168.1.0/24') is True

def test_outside_subnet():
    assert is_ip_in_network('10.0.0.1', '192.168.1.0/24') is False
