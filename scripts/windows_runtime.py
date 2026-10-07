"""Private Windows profile: prepare, supervise owned processes, verify HTTPS.

The PowerShell entrypoint holds the profile mutex and sets its ACL for this
controller's entire lifetime. Never use the legacy repository data directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
import webbrowser
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def free_port(start, excluded=()):
    for port in range(start, min(start + 100, 65536)):
        if port in excluded:
            continue
        try:
            with socket.socket() as sock:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    raise ValueError("没有可用端口，请关闭占用程序后重试。")


def write_json(path, value):
    temporary = path.with_suffix(".pending")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    temporary.replace(path)


def profile_config(profile, zone=None):
    path = profile / "profile.json"
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
        if set(value) != {"version", "secret", "time_zone", "web_port", "backend_port"} or value["version"] != 1:
            raise ValueError("运行配置格式不兼容；不会覆盖已有配置。")
        if not isinstance(value["secret"], str) or len(value["secret"]) < 50:
            raise ValueError("运行密钥无效。")
        if any(type(value[key]) is not int or not 1024 <= value[key] <= 65535 for key in ("web_port", "backend_port")) or value["web_port"] == value["backend_port"]:
            raise ValueError("端口配置无效。")
        ZoneInfo(value["time_zone"])
        return value
    if not zone:
        raise ValueError("首次安装必须确认家庭 IANA 时区。")
    ZoneInfo(zone)
    web_port = free_port(8443)
    value = {"version": 1, "secret": secrets.token_urlsafe(64), "time_zone": zone,
             "web_port": web_port, "backend_port": free_port(8800, [web_port])}
    write_json(path, value)
    return value


def checked_lan(address, cidr):
    from scripts.macos_setup import checked_network
    return checked_network(address, cidr)


def environment(profile, config, lan=None):
    values = {k: v for k, v in os.environ.items() if not k.startswith(("SHIJIN_", "DJANGO_"))}
    hosts = ["localhost"] + ([lan[0]] if lan else [])
    values.update({"DJANGO_SETTINGS_MODULE": "config.settings.prod", "PYTHONUTF8": "1",
        "SHIJIN_SECRET_KEY": config["secret"], "SHIJIN_TIME_ZONE": config["time_zone"],
        "SHIJIN_ALLOWED_HOSTS": ",".join(hosts),
        "SHIJIN_CSRF_TRUSTED_ORIGINS": ",".join(f"https://{h}:{config['web_port']}" for h in hosts),
        "SHIJIN_DATA_DIR": str(profile / "data"), "SHIJIN_STATIC_ROOT": str(profile / "static"),
        "SHIJIN_WAITRESS_PORT": str(config["backend_port"]), "SHIJIN_RECIPE_PROVIDER": "off"})
    return values


def management(env, *args):
    subprocess.run([sys.executable, str(ROOT / "manage.py"), *args], cwd=ROOT, env=env, check=True)


def activate_environment(profile, config):
    values = environment(profile, config)
    for key in tuple(os.environ):
        if key.startswith(("SHIJIN_", "DJANGO_")):
            del os.environ[key]
    os.environ.update(values)


def backup(profile):
    database = profile / "data" / "app.sqlite3"
    if not database.exists():
        return
    from core.management.commands.backup_household import create_private_backup
    # The shared backup implementation handles a database interrupted before
    # its recipe-media migration as well as a fully initialized household.
    target, count = create_private_backup(database, profile / "data" / "recipe_media", profile / "data" / "backups")
    print(f"迁移前备份：{target.name}，附件 {count} 个。", flush=True)


def prepare(profile, config, *, non_interactive=False):
    env = environment(profile, config)
    (profile / "data").mkdir(exist_ok=True)
    fingerprint = hashlib.sha256((ROOT / "requirements.lock").read_bytes())
    for folder in ("core", "inventory", "meals", "shopping", "config", "templates", "static", "scripts"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".ps1", ".html", ".css", ".js", ".json", ".svg"}:
                fingerprint.update(path.relative_to(ROOT).as_posix().encode())
                fingerprint.update(path.read_bytes())
    revision = fingerprint.hexdigest()
    prepared = profile / "prepared.json"
    previous = json.loads(prepared.read_text(encoding="utf-8")) if prepared.exists() else {}
    if previous.get("revision") != revision:
        backup(profile)
    management(env, "migrate", "--noinput")
    management(env, "check", "--deploy")
    management(env, "collectstatic", "--noinput")
    from scripts.install_yolo_food import install
    install(profile / "data")
    write_json(prepared, {"revision": revision})
    if non_interactive:
        print("准备完成；非交互模式未创建账号，也没有安装信任证书或开放局域网。", flush=True)
    else:
        management(env, "setup_household", "--time-zone", config["time_zone"])


def caddy_config(profile, config, lan=None):
    # Reuse the existing route limits, static policy and trusted proxy headers.
    source = (ROOT / "config" / "Caddyfile.windows").read_text(encoding="utf-8")
    sites = f"https://localhost:{config['web_port']}"
    bindings, allowed = "127.0.0.1", "127.0.0.1/32"
    if lan:
        ip, cidr = checked_lan(*lan)
        sites += f", https://{ip}:{config['web_port']}"
        bindings += f" {ip}"
        allowed += f" {cidr}"
    source = source.replace("https://{$SHIJIN_LAN_IP}:8443", sites)
    source = source.replace("{$SHIJIN_LAN_IP}", bindings).replace("{$SHIJIN_ALLOWED_CIDR}", allowed)
    source = source.replace("127.0.0.1:8000", f"127.0.0.1:{config['backend_port']}")
    # Caddyfile quoted paths: do not allow interpolation, quotes or newlines.
    for key, path in (("SHIJIN_STATIC_ROOT", profile / "static"), ("SHIJIN_CADDY_STORAGE", profile / "caddy")):
        value = path.as_posix()
        if any(char in value for char in ('"', '\n', '\r', '$', '`')):
            raise ValueError("安装路径含 Caddyfile 不支持的字符。")
        source = source.replace("{$" + key + "}", value)
    result = profile / "Caddyfile"
    result.write_text(source, encoding="utf-8")
    return result


def probe(url, ca):
    context = ssl.create_default_context(cafile=str(ca))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    with opener.open(url, timeout=3) as response:
        if response.status != 200 or json.load(response) != {"status": "ok"}:
            raise ValueError("HTTPS 健康响应无效。")


def serve(profile, config, caddy, *, lan=None, smoke=False):
    expected_network = None
    if lan:
        saved = json.loads((profile / "lan.json").read_text(encoding="utf-8-sig"))
        if (saved['ip'], saved['cidr']) != lan:
            raise ValueError("局域网参数未经过本次确认。")
        expected_network = saved['snapshot']
        if network_snapshot(lan[0]) != expected_network:
            raise ValueError("网络已变化，请重新选择并确认可信网络。")
    for port in (config["web_port"], config["backend_port"]):
        if free_port(port) != port:
            raise ValueError(f"端口 {port} 已被占用；请关闭原运行窗口，不会结束其他程序。")
    env = environment(profile, config, lan)
    caddy_env = {key: val for key, val in os.environ.items() if not key.startswith(("SHIJIN_", "DJANGO_"))}
    file = caddy_config(profile, config, lan)
    validation = subprocess.run([str(caddy), "validate", "--config", str(file), "--adapter", "caddyfile"],
        env=caddy_env, capture_output=True)
    (profile / "caddy-validation.log").write_bytes(validation.stdout + validation.stderr)
    if validation.returncode:
        raise ValueError("Caddy 配置验证失败，请查看私有目录 caddy-validation.log。")
    print("Caddy 配置验证通过。", flush=True)
    children = []
    creation = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    log = profile / "server.log"
    # New bounded log per launch. No access logging or credentials passed to Caddy.
    with log.open("w", encoding="utf-8") as output:
        try:
            children.append(subprocess.Popen([sys.executable, "-m", "scripts.serve_waitress"], cwd=ROOT,
                env=env, stdout=output, stderr=output, creationflags=creation))
            children.append(subprocess.Popen([str(caddy), "run", "--config", str(file), "--adapter", "caddyfile"],
                env=caddy_env, stdout=output, stderr=output, creationflags=creation))
            url = f"https://localhost:{config['web_port']}"
            ca = profile / "caddy" / "pki" / "authorities" / "local" / "root.crt"
            deadline = time.monotonic() + 45
            while True:
                if any(child.poll() is not None for child in children):
                    raise ValueError(f"服务启动失败，检查本机私有日志：{log}")
                try:
                    probe(url + "/health/", ca)
                    if lan:
                        probe(f"https://{lan[0]}:{config['web_port']}/health/", ca)
                    break
                except (OSError, ValueError):
                    if time.monotonic() >= deadline:
                        raise ValueError(f"HTTPS 健康检查超时，未声明部署成功。检查：{log}")
                    time.sleep(.3)
            print("本机 HTTPS 严格校验通过：" + url + "/health/", flush=True)
            if smoke:
                print("SMOKE_OK：未修改系统证书信任，测试后关闭本轮服务。", flush=True)
                return
            der = ssl.PEM_cert_to_DER_cert(ca.read_text(encoding="ascii"))
            fingerprint = hashlib.sha256(der).hexdigest().upper()
            print("本家庭公开根证书 SHA-256：" + ":".join(fingerprint[i:i+2] for i in range(0,64,2)), flush=True)
            print("证书文件：" + str(ca), flush=True)
            # Existing trust is checked normally; never disable verification.
            trusted = False
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(url + "/health/", timeout=3) as response:
                    trusted = response.status == 200
            except OSError:
                pass
            if not trusted:
                answer = input("是否将上述本家庭 CA 加入当前 Windows 用户信任？这会信任它签发的证书。[y/N]：").strip().lower()
                if answer == "y":
                    subprocess.run(["certutil.exe", "-user", "-addstore", "Root", str(ca)], check=True)
                    trusted = True
            print("应用入口：" + url, flush=True)
            if lan:
                print(f"家庭局域网：https://{lan[0]}:{config['web_port']}/（其他设备需人工信任同一公开根证书）", flush=True)
            if trusted:
                webbrowser.open(url + "/welcome/")
            else:
                print("尚未信任根证书；请勿在证书警告后输入账号密码。", flush=True)
            print("保持此窗口运行。按 Ctrl+C 停止本轮 Waitress 和 Caddy。", flush=True)
            next_network_check = time.monotonic()
            while True:
                if any(child.poll() is not None for child in children):
                    raise ValueError(f"服务意外退出，其余服务将停止。检查：{log}")
                if lan and time.monotonic() >= next_network_check:
                    if network_snapshot(lan[0]) != expected_network:
                        raise ValueError("检测到网络变化，局域网服务已停止。新网络需重新确认。")
                    next_network_check = time.monotonic() + 5
                time.sleep(1)
        finally:
            # Popen handles identify only our own children, never arbitrary PIDs.
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
            for child in children:
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


def network_snapshot(address):
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    result = subprocess.check_output([str(powershell), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "windows_network.ps1"),
        "-Address", address], timeout=10)
    return json.loads(result.decode("utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "serve", "smoke", "account", "backup"))
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--time-zone")
    parser.add_argument("--caddy", type=Path)
    parser.add_argument("--lan-ip")
    parser.add_argument("--cidr")
    parser.add_argument("--non-interactive", action="store_true")
    args = parser.parse_args()
    profile = args.profile.resolve()
    config = profile_config(profile, args.time_zone)
    activate_environment(profile, config)
    import django
    django.setup()
    if args.action == "prepare":
        prepare(profile, config, non_interactive=args.non_interactive)
    elif args.action == "backup":
        backup(profile)
    elif args.action == "account":
        print("账号维护：1 重设密码 / 2 解锁账号 / 3 创建管理员 / 4 启用账号 / 5 禁用账号")
        choice = input("选择：").strip()
        username = input("账号名：").strip()
        commands = {"1": ["password", username], "2": ["unlock", "--username", username],
            "3": ["create", username, "--role", "admin"], "4": ["enable", username], "5": ["disable", username]}
        if choice not in commands or not username or username.startswith("-"):
            raise ValueError("账号维护输入无效。")
        management(environment(profile, config), "manage_member", *commands[choice])
    else:
        if not args.caddy or not args.caddy.is_file():
            raise ValueError("Caddy 未安装。")
        lan = checked_lan(args.lan_ip, args.cidr) if args.lan_ip and args.cidr else None
        from scripts.windows_job import protect_process_tree
        protect_process_tree()
        serve(profile, config, args.caddy, lan=lan, smoke=args.action == "smoke")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n本轮应用已停止，家庭数据保留。")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"操作未完成：{exc}", file=sys.stderr)
        raise SystemExit(1)
