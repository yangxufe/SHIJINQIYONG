"""Create or rebind a private, local macOS runtime configuration."""

from __future__ import annotations

import argparse
import ipaddress
import os
import secrets
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RFC1918 = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def checked_network(address: str, cidr: str) -> tuple[str, str]:
    try:
        ip = ipaddress.IPv4Address(address)
        network = ipaddress.IPv4Network(cidr, strict=True)
    except ipaddress.AddressValueError as exc:
        raise ValueError("请输入有效的 IPv4 地址和 CIDR 子网。") from exc
    except ipaddress.NetmaskValueError as exc:
        raise ValueError("请输入有效的 CIDR 子网掩码。") from exc
    if not any(ip in private and network.subnet_of(private) for private in RFC1918):
        raise ValueError("仅允许家庭私有 IPv4 子网。")
    if ip not in network or not 16 <= network.prefixlen <= 30:
        raise ValueError("电脑地址必须在指定的家庭子网内，掩码须为 /16 至 /30。")
    return str(ip), str(network)


def _write_private(path: Path, content: str, *, replace: bool) -> None:
    if path.is_symlink():
        raise ValueError("运行配置不能是符号链接。")
    if replace:
        handle, temporary = tempfile.mkstemp(prefix=".runtime-", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    else:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.chmod(path, 0o600)


def configure(root: Path, address: str, cidr: str, *, update_ip: bool = False, time_zone: str = "UTC") -> Path:
    ip, network = checked_network(address, cidr)
    root = root.resolve()
    data = root / "data"
    data.mkdir(mode=0o700, exist_ok=True)
    if data.is_symlink():
        raise ValueError("私有 data 目录不能是符号链接。")
    os.chmod(data, 0o700)
    runtime = data / "runtime.env"
    values = {
        "SHIJIN_ALLOWED_HOSTS": ip,
        "SHIJIN_CSRF_TRUSTED_ORIGINS": f"https://{ip}:8443",
        "SHIJIN_LAN_IP": ip,
        "SHIJIN_ALLOWED_CIDR": network,
    }
    if update_ip:
        if not runtime.is_file() or runtime.is_symlink():
            raise ValueError("原运行配置不存在或不是普通文件，不能更新地址。")
        if os.name == "posix" and runtime.stat().st_mode & 0o077:
            raise ValueError("原运行配置权限过宽；先改为仅本人可读写。")
        lines = runtime.read_text(encoding="utf-8").splitlines()
        keys = {line.split("=", 1)[0] for line in lines if line and not line.startswith("#")}
        if not set(values).issubset(keys):
            raise ValueError("原运行配置缺少地址字段。")
        updated = [f"{line.split('=', 1)[0]}={values[line.split('=', 1)[0]]}"
                   if line.split("=", 1)[0] in values else line for line in lines]
        _write_private(runtime, "\n".join(updated) + "\n", replace=True)
        return runtime
    if runtime.exists() or runtime.is_symlink():
        raise ValueError("运行配置已存在；不会覆盖密钥或数据。更换网络请使用 --update-ip。")
    try:
        ZoneInfo(time_zone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("时区必须是本机可用的 IANA 名称。") from exc
    caddy_storage = data / "caddy"
    caddy_storage.mkdir(mode=0o700, exist_ok=True)
    if caddy_storage.is_symlink():
        raise ValueError("Caddy 私有目录不能是符号链接。")
    os.chmod(caddy_storage, 0o700)
    media = data / "recipe_media"
    media.mkdir(mode=0o700, exist_ok=True)
    if media.is_symlink():
        raise ValueError("家庭附件目录不能是符号链接。")
    os.chmod(media, 0o700)
    lines = {
        "SHIJIN_SECRET_KEY": secrets.token_urlsafe(64),
        **values,
        "SHIJIN_TIME_ZONE": time_zone,
        "SHIJIN_DATA_DIR": str(data),
        "SHIJIN_STATIC_ROOT": str(root / "collected_static"),
        "SHIJIN_CADDY_STORAGE": str(caddy_storage),
        "SHIJIN_RECIPE_PROVIDER": "off",
    }
    if any("\n" in value or "\r" in value for value in lines.values()):
        raise ValueError("运行路径或配置含无效换行。")
    _write_private(runtime, "".join(f"{key}={value}\n" for key, value in lines.items()), replace=False)
    return runtime


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize a private macOS LAN configuration.")
    parser.add_argument("ip", help="Mac current trusted Wi-Fi IPv4 address")
    parser.add_argument("cidr", help="confirmed household subnet, e.g. 192.168.1.0/24")
    parser.add_argument("--update-ip", action="store_true", help="preserve secret and data, change only confirmed IP/subnet")
    parser.add_argument("--time-zone", default="UTC", help="IANA time zone, e.g. Asia/Shanghai")
    args = parser.parse_args()
    try:
        configure(PROJECT_ROOT, args.ip, args.cidr, update_ip=args.update_ip, time_zone=args.time_zone)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"配置未修改：{exc}\n")
    print("本机私有配置已保存；密钥未输出。" if not args.update_ip else "已更新确认的家庭 IP 与子网；密钥和数据保留。")


if __name__ == "__main__":
    main()
