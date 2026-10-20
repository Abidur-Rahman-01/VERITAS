"""CIDR subnet checker."""
import ipaddress

def is_ip_in_network(ip_str: str, cidr_str: str) -> bool:
    # BUG: Inverted boolean logic
    net = ipaddress.ip_network(cidr_str, strict=False)
    ip = ipaddress.ip_address(ip_str)
    return ip in net
