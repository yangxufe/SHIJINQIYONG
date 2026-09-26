"""Load the private allowlisted runtime before Mac management or local servers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = PROJECT_ROOT / "data" / "runtime.env"
ALLOWED = {
    "SHIJIN_SECRET_KEY", "SHIJIN_ALLOWED_HOSTS", "SHIJIN_CSRF_TRUSTED_ORIGINS",
    "SHIJIN_TIME_ZONE", "SHIJIN_DATA_DIR", "SHIJIN_STATIC_ROOT", "SHIJIN_CADDY_STORAGE",
    "SHIJIN_LAN_IP", "SHIJIN_ALLOWED_CIDR", "SHIJIN_RECIPE_PROVIDER",
    "SHIJIN_RECIPE_MODEL", "SHIJIN_RECIPE_API_KEY",
}
CADDY_FIELDS = {"SHIJIN_LAN_IP", "SHIJIN_ALLOWED_CIDR", "SHIJIN_STATIC_ROOT", "SHIJIN_CADDY_STORAGE"}


def load_runtime(path: Path = RUNTIME) -> dict[str, str]:
    if not path.is_file() or path.is_symlink() or (os.name == "posix" and path.stat().st_mode & 0o077):
        raise ValueError("私有运行配置缺失或权限过宽；要求仅本人可读写。")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Z_]+)=(.*)", line)
        if not match or match.group(1) not in ALLOWED or not match.group(2):
            raise ValueError("私有运行配置包含未知或空字段。")
        values[match.group(1)] = match.group(2)
    required = {"SHIJIN_SECRET_KEY", "SHIJIN_ALLOWED_HOSTS", "SHIJIN_CSRF_TRUSTED_ORIGINS",
                "SHIJIN_DATA_DIR", "SHIJIN_STATIC_ROOT", "SHIJIN_CADDY_STORAGE",
                "SHIJIN_LAN_IP", "SHIJIN_ALLOWED_CIDR"}
    if not required.issubset(values):
        raise ValueError("私有运行配置不完整。")
    return values


def current_interface_has_ip(address: str) -> bool:
    output = subprocess.check_output(["ifconfig"], text=True)
    return re.search(rf"\binet\s+{re.escape(address)}(?=\s)", output) is not None


def environment_for(mode: str, values: dict[str, str], inherited: dict[str, str]) -> dict[str, str]:
    environment = {key: value for key, value in inherited.items() if not key.startswith("SHIJIN_")}
    environment.update({key: value for key, value in values.items()
                        if mode not in {"caddy", "caddy-adapt"} or key in CADDY_FIELDS})
    if mode not in {"caddy", "caddy-adapt"}:
        environment["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
    return environment


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"manage", "waitress", "worker", "caddy", "caddy-adapt"}:
        raise SystemExit("用法：macos_runtime.py manage <管理命令> | waitress | worker | caddy | caddy-adapt")
    mode = sys.argv[1]
    values = load_runtime()
    environment = environment_for(mode, values, os.environ)
    os.chdir(PROJECT_ROOT)
    if mode == "manage":
        if len(sys.argv) < 3:
            raise SystemExit("缺少 Django 管理命令。")
        os.execve(sys.executable, [sys.executable, str(PROJECT_ROOT / "manage.py"),
                                  *sys.argv[2:], "--settings=config.settings.prod"], environment)
    if mode in {"waitress", "worker"}:
        command = ([sys.executable, "-m", "scripts.serve_waitress"] if mode == "waitress"
                   else [sys.executable, str(PROJECT_ROOT / "manage.py"), "run_recipe_worker",
                         "--settings=config.settings.prod"])
        os.execve(sys.executable, command, environment)
    if not current_interface_has_ip(values["SHIJIN_LAN_IP"]):
        raise SystemExit("当前网卡没有已确认的家庭 IP；Caddy 未启动。换网后先核对并更新配置。")
    caddy = shutil.which("caddy")
    if caddy is None:
        raise SystemExit("找不到 Caddy；请先安装并确认 caddy 在 PATH 中。")
    config = str(PROJECT_ROOT / "config" / "Caddyfile.macos")
    command = ([caddy, "run", "--config", config, "--adapter", "caddyfile"] if mode == "caddy"
               else [caddy, "adapt", "--config", config, "--adapter", "caddyfile", "--validate"])
    os.execve(caddy, command, environment)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
