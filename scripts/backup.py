#!/usr/bin/env python3
"""
PC Guardian - 备份与回档模块
所有高风险操作前先备份，支持随时回退。

备份策略：
- 文件/目录 → 复制到 ~/.pc-guardian/backups/{timestamp}/
- 系统设置 → 导出当前值到 JSON
- 操作日志 → ~/.pc-guardian/operations.jsonl
"""

import os
import sys
import shutil
import json
import hashlib
import subprocess
import platform
from datetime import datetime
from pathlib import Path

SYSTEM = platform.system()
BACKUP_ROOT = os.path.expanduser("~/.pc-guardian/backups")
LOG_FILE = os.path.expanduser("~/.pc-guardian/operations.jsonl")
STATE_DIR = os.path.expanduser("~/.pc-guardian/state")


def ensure_dirs():
    """确保备份目录存在"""
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)


def timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def operation_id():
    return datetime.now().strftime("%Y%m%d%H%M%S%f")


def log_operation(op_type, action, target, status, details=None, backup_path=None):
    """记录操作日志"""
    ensure_dirs()
    entry = {
        "id": operation_id(),
        "timestamp": datetime.now().isoformat(),
        "type": op_type,       # cleanup / file_move / file_delete / sys_setting / skill_update
        "action": action,      # backup / execute / rollback
        "target": target,      # 操作对象
        "status": status,      # success / failed / dry_run
        "backup_path": backup_path,
        "details": details or {},
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def backup_file_or_dir(path):
    """备份单个文件或目录"""
    ensure_dirs()
    path = os.path.expanduser(os.path.expandvars(path))
    if not os.path.exists(path):
        return None, "路径不存在"

    ts = timestamp()
    name = os.path.basename(path)
    backup_name = f"{name}.{ts}.bak"
    backup_path = os.path.join(BACKUP_ROOT, ts, backup_name)
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)

    try:
        if os.path.isdir(path):
            shutil.copytree(path, backup_path, symlinks=True)
        else:
            shutil.copy2(path, backup_path)

        # 计算校验和
        size = os.path.getsize(backup_path) if os.path.isfile(backup_path) else dir_size(backup_path)

        log_operation("backup", "backup", path, "success", backup_path=backup_path)
        return backup_path, f"已备份到 {backup_path}"
    except Exception as e:
        log_operation("backup", "backup", path, "failed", details={"error": str(e)})
        return None, f"备份失败: {e}"


def backup_system_setting(setting_name, get_cmd, desc=""):
    """备份系统设置（通过命令获取当前值）"""
    ensure_dirs()
    try:
        result = subprocess.run(get_cmd, shell=True, capture_output=True, text=True, timeout=10)
        current_value = result.stdout.strip() if result.returncode == 0 else None

        setting_file = os.path.join(STATE_DIR, f"{setting_name}.json")
        entry = {
            "name": setting_name,
            "description": desc,
            "value": current_value,
            "cmd": get_cmd,
            "timestamp": datetime.now().isoformat(),
        }

        # 追加到设置历史
        history = []
        if os.path.exists(setting_file):
            with open(setting_file, "r") as f:
                history = json.load(f)
        history.append(entry)
        with open(setting_file, "w") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        log_operation("sys_setting", "backup", setting_name, "success")
        return True, current_value
    except Exception as e:
        log_operation("sys_setting", "backup", setting_name, "failed", details={"error": str(e)})
        return False, str(e)


def rollback(backup_path):
    """从备份恢复"""
    ensure_dirs()
    if not backup_path or not os.path.exists(backup_path):
        return False, f"备份不存在: {backup_path}"

    try:
        # 从备份路径推断原始路径
        # 格式: ~/.pc-guardian/backups/{timestamp}/{name}.{ts}.bak
        parts = backup_path.split("/")
        backup_name = parts[-1]  # name.ts.bak
        # 去掉 .ts.bak 后缀
        parts2 = backup_name.split(".")
        original_name = parts2[0]

        # 查找操作日志中的原始路径
        original_path = None
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                for line in f:
                    entry = json.loads(line.strip())
                    if entry.get("backup_path") == backup_path:
                        original_path = entry.get("target")
                        break

        if not original_path:
            return False, f"无法从日志中找到原始路径，请手动恢复: {backup_path}"

        # 恢复
        if os.path.isdir(backup_path):
            if os.path.exists(original_path):
                shutil.rmtree(original_path, ignore_errors=True)
            shutil.copytree(backup_path, original_path, symlinks=True)
        else:
            shutil.copy2(backup_path, original_path)

        log_operation("rollback", "rollback", original_path, "success", backup_path=backup_path)
        return True, f"已恢复到 {original_path}"
    except Exception as e:
        log_operation("rollback", "rollback", backup_path, "failed", details={"error": str(e)})
        return False, f"恢复失败: {e}"


def list_backups(limit=20):
    """列出最近的备份"""
    ensure_dirs()
    backups = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("action") == "backup" and entry.get("status") == "success":
                        backups.append(entry)
                except json.JSONDecodeError:
                    continue
    backups.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return backups[:limit]


def dir_size(path):
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat().st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += dir_size(entry.path)
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return total


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PC Guardian - 备份与回档")
    sub = parser.add_subparsers(dest="command")

    backup_parser = sub.add_parser("backup", help="备份文件或目录")
    backup_parser.add_argument("path", help="要备份的路径")

    rollback_parser = sub.add_parser("rollback", help="从备份恢复")
    rollback_parser.add_argument("backup_path", help="备份路径")

    list_parser = sub.add_parser("list", help="列出最近备份")

    args = parser.parse_args()

    if args.command == "backup":
        path, msg = backup_file_or_dir(args.path)
        print(msg)
    elif args.command == "rollback":
        ok, msg = rollback(args.backup_path)
        print(msg)
    elif args.command == "list":
        backups = list_backups()
        for b in backups:
            print(f"  {b['timestamp']}  {b['target']}  →  {b.get('backup_path', 'N/A')}")
    else:
        parser.print_help()
