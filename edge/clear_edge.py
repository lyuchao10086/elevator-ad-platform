#!/usr/bin/env python3
"""One-click clear all user tables in edge.db without dropping schema.

Default behavior:
- Load `config.json` from the same directory as this script.
- Resolve `db_path` relative to the edge directory.
- Delete all rows from every non-SQLite internal table.
- Reset autoincrement counters when present.

Usage:
  python clear_edge_db.py
  python clear_edge_db.py --db-path resources/edge.db
  python clear_edge_db.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path


def load_db_path(edge_dir: Path, explicit_db_path: str | None) -> Path:
    if explicit_db_path:
        db_path = Path(explicit_db_path)
        if not db_path.is_absolute():
            db_path = (edge_dir / db_path).resolve()
        return db_path

    config_path = edge_dir / "config.json"
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as fh:
            config = json.load(fh)
        db_path = Path(config.get("db_path", "resources/edge.db"))
        if not db_path.is_absolute():
            db_path = (edge_dir / db_path).resolve()
        return db_path

    return (edge_dir / "resources" / "edge.db").resolve()


def list_user_tables(conn: sqlite3.Connection) -> list[str]:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    )
    return [row[0] for row in cursor.fetchall()]


def table_has_rows(conn: sqlite3.Connection, table_name: str) -> bool:
    cursor = conn.execute(f'SELECT 1 FROM "{table_name}" LIMIT 1;')
    return cursor.fetchone() is not None


def clear_database(db_path: Path, dry_run: bool = False) -> list[str]:
    if not db_path.exists():
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")

    actions: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF;")
        tables = list_user_tables(conn)

        if not tables:
            actions.append("未发现可清空的用户表")
            return actions

        if dry_run:
            actions.append(f"发现 {len(tables)} 张用户表: {', '.join(tables)}")
            return actions

        conn.execute("BEGIN;")
        for table_name in tables:
            conn.execute(f'DELETE FROM "{table_name}";')
            actions.append(f"已清空表: {table_name}")

        # 清理自增计数器，避免下次插入 ID 继续累计。
        try:
            conn.execute("DELETE FROM sqlite_sequence;")
            actions.append("已重置 sqlite_sequence")
        except sqlite3.OperationalError:
            # 某些数据库没有 autoincrement 表，忽略即可。
            pass

        conn.commit()

        # VACUUM 必须在事务外执行。
        try:
            conn.execute("VACUUM;")
            actions.append("已执行 VACUUM")
        except sqlite3.OperationalError:
            # 某些场景下 VACUUM 可能失败，但不影响清空结果。
            pass

        return actions
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清空 edge.db 中所有用户表数据")
    parser.add_argument("--db-path", help="数据库路径，默认读取 config.json 里的 db_path")
    parser.add_argument("--dry-run", action="store_true", help="只预览将被清空的表，不执行删除")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    edge_dir = Path(__file__).resolve().parent
    db_path = load_db_path(edge_dir, args.db_path)

    try:
        actions = clear_database(db_path, dry_run=args.dry_run)
    except Exception as exc:
        print(f"清空数据库失败: {exc}", file=sys.stderr)
        return 1

    print(f"数据库: {db_path}")
    for action in actions:
        print(action)

    if args.dry_run:
        print("dry-run 完成，未执行删除。")
    else:
        print("清空完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
