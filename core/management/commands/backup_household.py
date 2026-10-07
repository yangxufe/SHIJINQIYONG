"""Back up the SQLite database and every referenced private recipe file together."""

import hashlib
import json
import os
import socket
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from meals.media import FILE_KEY_PATTERN


def create_private_backup(database_path, media_dir, backups_dir):
    database_path = Path(database_path).resolve()
    media_dir = Path(media_dir).resolve()
    backups_dir = Path(backups_dir).resolve()
    if not database_path.is_file() or backups_dir == database_path.parent:
        raise ValueError("Invalid backup source or destination")
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    staging = backups_dir / (".incomplete-" + stamp)
    target = backups_dir / ("household-" + stamp)
    if staging.exists() or target.exists():
        raise FileExistsError("Backup target already exists")
    staging.mkdir()
    database_copy = staging / "app.sqlite3"
    with closing(sqlite3.connect(database_path)) as source, closing(sqlite3.connect(database_copy)) as destination:
        source.backup(destination)
    with closing(sqlite3.connect(database_copy)) as check:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or check.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Backed-up database failed integrity checks")
        media_table = check.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meals_recipemedia'").fetchone()
        rows = check.execute("SELECT file_key, sha256 FROM meals_recipemedia ORDER BY file_key").fetchall() if media_table else []
    copied = staging / "recipe_media"
    copied.mkdir()
    for key, expected_digest in rows:
        if not FILE_KEY_PATTERN.fullmatch(key):
            raise ValueError("Invalid media key in database")
        source_file = media_dir / key
        if not source_file.is_file() or source_file.is_symlink():
            raise FileNotFoundError("A referenced private media file is missing")
        destination_file = copied / key
        digest = hashlib.sha256()
        with source_file.open("rb") as source, destination_file.open("xb") as destination:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
                destination.write(chunk)
        if digest.hexdigest() != expected_digest:
            raise ValueError("A referenced media file failed its checksum")
    (staging / "manifest.json").write_text(json.dumps({"media_files": len(rows), "database": "app.sqlite3"}), encoding="utf-8")
    os.replace(staging, target)
    return target, len(rows)


class Command(BaseCommand):
    help = "Back up the private SQLite database and recipe media while Waitress is stopped."

    def handle(self, *args, **options):
        with socket.socket() as connection:
            connection.settimeout(0.5)
            if connection.connect_ex(("127.0.0.1", 8000)) == 0:
                raise CommandError("请先停止 Waitress，再备份数据库与菜谱附件，避免备份期间有人修改。")
        data_dir = Path(settings.DATA_DIR).resolve()
        database_path = Path(settings.DATABASES["default"]["NAME"]).resolve()
        if data_dir not in database_path.parents:
            raise CommandError("数据库路径不在配置的数据目录下。")
        try:
            target, media_count = create_private_backup(database_path, data_dir / "recipe_media", data_dir / "backups")
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise CommandError("备份失败；私有目录中可能保留 .incomplete 快照，请检查后处理。") from exc
        self.stdout.write(self.style.SUCCESS(f"备份完成：{target.name}，附件 {media_count} 个。请将整个目录存放到受保护的异设备。"))
