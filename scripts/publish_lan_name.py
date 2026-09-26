"""Publish the fixed household hostname only while the network guard is active."""

from __future__ import annotations

import ipaddress
import json
import socket
import time
from pathlib import Path

import ifaddr
from zeroconf import IPVersion, ServiceInfo, Zeroconf


STATE = Path(r"C:\Program Files\ShiJinQiYong\NetworkGuard\active.json")
HOSTNAME = "shijinqiyong.local."
SERVICE_NAME = "ShiJinQiYong._https._tcp.local."
SERVICE_TYPE = "_https._tcp.local."


def wlan_ipv4_addresses(interface_guid: str) -> set[str]:
    addresses: set[str] = set()
    for adapter in ifaddr.get_adapters():
        if adapter.name.upper() != interface_guid.upper():
            continue
        for item in adapter.ips:
            if isinstance(item.ip, str):
                addresses.add(item.ip)
    return addresses


def desired_ip() -> str | None:
    try:
        payload = json.loads(STATE.read_text(encoding="utf-8"))
        ip = payload.get("ip")
        interface_guid = payload.get("interface_guid")
        updated_at = int(payload.get("updated_at", 0))
        if not isinstance(ip, str) or not isinstance(interface_guid, str) or time.time() - updated_at > 15:
            return None
        if not ipaddress.IPv4Address(ip).is_private or ip not in wlan_ipv4_addresses(interface_guid):
            return None
        return ip
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def main() -> None:
    current_ip: str | None = None
    zc: Zeroconf | None = None
    info: ServiceInfo | None = None
    try:
        while True:
            target = desired_ip()
            if target != current_ip:
                if zc is not None:
                    if info is not None:
                        zc.unregister_service(info)
                    zc.close()
                    zc = None
                    info = None
                    current_ip = None
                if target is not None:
                    info = ServiceInfo(
                        SERVICE_TYPE,
                        SERVICE_NAME,
                        addresses=[socket.inet_aton(target)],
                        port=8443,
                        properties={"path": "/"},
                        server=HOSTNAME,
                    )
                    zc = Zeroconf(interfaces=[target], ip_version=IPVersion.V4Only)
                    zc.register_service(info, allow_name_change=False)
                    current_ip = target
            time.sleep(2)
    finally:
        if zc is not None:
            if info is not None:
                zc.unregister_service(info)
            zc.close()


if __name__ == "__main__":
    main()
