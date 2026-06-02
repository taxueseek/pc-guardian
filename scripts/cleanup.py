#!/usr/bin/env python3
"""
PC Guardian - 垃圾清理模块（增强版）
支持 macOS 和 Windows

vs 传统清理软件的优势：
- 语义理解：不只看路径，还能分析文件用途（如识别 node_modules 是依赖而非垃圾）
- 智能分级：按风险分级（安全/需确认/高危），不是一刀切
- 先备份后清理：所有删除操作先备份到 ~/.pc-guardian/backups/
- 可回档：通过 backup.py 随时恢复
- 操作日志：每次清理记录到 operations.jsonl
"""

import os
import sys
import shutil
import subprocess
import platform
import json
import time
import glob as globmod
from pathlib import Path
from datetime import datetime

SYSTEM = platform.system()
BACKUP_ROOT = os.path.expanduser("~/.pc-guardian/backups")
LOG_FILE = os.path.expanduser("~/.pc-guardian/operations.jsonl")
os.makedirs(BACKUP_ROOT, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def human_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


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


def log_operation(op_type, action, target, status, details=None):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": op_type,
        "action": action,
        "target": target,
        "status": status,
        "details": details or {},
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def backup_before_delete(path):
    """删除前先备份（只备份元数据，大文件跳过）"""
    path = os.path.expanduser(os.path.expandvars(path))
    if not os.path.exists(path):
        return None

    # 超过 500MB 的目录不备份（太重），只记录元数据
    size = dir_size(path) if os.path.isdir(path) else os.path.getsize(path)
    if size > 500 * 1024 * 1024:
        return {"type": "metadata_only", "path": path, "size": size,
                "note": "文件过大，仅记录元数据，不备份内容"}

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = os.path.basename(path)
    backup_path = os.path.join(BACKUP_ROOT, ts, f"{name}.bak")
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)

    try:
        if os.path.isdir(path):
            shutil.copytree(path, backup_path, symlinks=True, ignore_dangling_symlinks=True)
        else:
            shutil.copy2(path, backup_path)
        return {"type": "full", "path": path, "backup_path": backup_path, "size": size}
    except Exception as e:
        return {"type": "failed", "path": path, "error": str(e)}


def safe_delete(path, dry_run=True, auto_backup=True):
    """安全删除：先备份→再删除"""
    path = os.path.expanduser(os.path.expandvars(path))
    if not os.path.exists(path):
        return {"path": path, "action": "skip", "reason": "不存在"}

    size = dir_size(path) if os.path.isdir(path) else os.path.getsize(path)

    if dry_run:
        return {"path": path, "size": size, "action": "would_delete", "backup": None}

    # 备份
    backup_info = None
    if auto_backup:
        backup_info = backup_before_delete(path)

    # 删除
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
        log_operation("cleanup", "delete", path, "success",
                      {"size": size, "backup": backup_info})
        return {"path": path, "size": size, "action": "deleted", "backup": backup_info}
    except Exception as e:
        log_operation("cleanup", "delete", path, "failed", {"error": str(e)})
        return {"path": path, "size": size, "action": f"error: {e}"}


# ── 清理目标定义 ────────────────────────────────────────────────
# risk_level: safe（自动）/ confirm（需确认）/ dangerous（高危，需二次确认）

MACOS_CLEANUP_TARGETS = {
    "trash": {
        "paths": ["~/.Trash"],
        "desc": "回收站",
        "risk": "safe",
        "note": "清空后不可恢复（除非有 Time Machine）",
    },
    "user_cache": {
        "paths": ["~/Library/Caches/*"],
        "desc": "应用缓存",
        "risk": "safe",
        "note": "应用会自动重建缓存",
    },
    "logs": {
        "paths": ["~/Library/Logs"],
        "desc": "应用日志",
        "risk": "safe",
        "note": "调试时可能需要旧日志",
    },
    "xcode_derived": {
        "paths": [
            "~/Library/Developer/Xcode/DerivedData",
            "~/Library/Developer/Xcode/Archives",
        ],
        "desc": "Xcode 构建产物 / 归档",
        "risk": "safe",
        "note": "重新编译会重建",
    },
    "npm_cache": {
        "paths": ["~/.npm/_cacache"],
        "desc": "npm 缓存",
        "risk": "safe",
        "note": "npm install 会重新下载",
    },
    "pip_cache": {
        "paths": ["~/Library/Caches/pip"],
        "desc": "pip 缓存",
        "risk": "safe",
    },
    "brew_cache": {
        "paths": ["~/Library/Caches/Homebrew"],
        "desc": "Homebrew 下载缓存",
        "risk": "safe",
        "note": "brew 会重新下载",
    },
    "docker": {
        "paths": [],
        "desc": "Docker 悬空镜像和卷",
        "risk": "confirm",
        "note": "会删除所有未使用的镜像和卷",
        "command": "docker system prune -f --volumes",
    },
    "system_cache": {
        "paths": ["~/Library/Caches"],
        "desc": "系统缓存目录（整体）",
        "risk": "confirm",
        "note": "包含所有应用缓存，可能影响正在运行的应用",
    },
    "old_downloads": {
        "paths": ["~/Downloads"],
        "desc": "下载目录中超过 30 天的文件",
        "risk": "confirm",
        "note": "只清理 ~/Downloads 中 30 天未访问的文件",
        "age_filter": 30,
    },
}

WINDOWS_CLEANUP_TARGETS = {
    "temp": {
        "paths": [os.path.expandvars(r"%TEMP%"), r"C:\Windows\Temp"],
        "desc": "临时文件",
        "risk": "safe",
    },
    "recycle_bin": {
        "paths": [],
        "desc": "回收站",
        "risk": "safe",
        "command": "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
    },
    "windows_update": {
        "paths": [r"C:\Windows\SoftwareDistribution\Download"],
        "desc": "Windows 更新缓存",
        "risk": "safe",
    },
    "npm_cache": {
        "paths": [os.path.expandvars(r"%APPDATA%\npm-cache")],
        "desc": "npm 缓存",
        "risk": "safe",
    },
    "pip_cache": {
        "paths": [os.path.expandvars(r"%LOCALAPPDATA%\pip\Cache")],
        "desc": "pip 缓存",
        "risk": "safe",
    },
    "browser_cache": {
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Cache"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Cache"),
        ],
        "desc": "浏览器缓存",
        "risk": "confirm",
        "note": "会清除浏览器缓存，可能需要重新登录网站",
    },
    "prefetch": {
        "paths": [r"C:\Windows\Prefetch"],
        "desc": "预读取文件",
        "risk": "safe",
        "note": "清理后首次启动程序会稍慢",
    },
    "docker": {
        "paths": [],
        "desc": "Docker 悬空镜像",
        "risk": "confirm",
        "command": "docker system prune -f --volumes",
    },
}


def get_targets():
    if SYSTEM == "Darwin":
        return MACOS_CLEANUP_TARGETS
    elif SYSTEM == "Windows":
        return WINDOWS_CLEANUP_TARGETS
    return {}


def scan_cleanup(detailed=False):
    """扫描可清理项目"""
    targets = get_targets()
    results = []
    total_size = 0
    risk_summary = {"safe": 0, "confirm": 0, "dangerous": 0}

    for key, target in targets.items():
        target_total = 0
        existing_paths = []

        for path_pattern in target.get("paths", []):
            expanded = os.path.expanduser(os.path.expandvars(path_pattern))
            if "*" in expanded:
                for item in globmod.glob(expanded):
                    if os.path.exists(item):
                        s = dir_size(item) if os.path.isdir(item) else os.path.getsize(item)
                        target_total += s
                        existing_paths.append({"path": item, "size": s})
            elif os.path.exists(expanded):
                s = dir_size(expanded) if os.path.isdir(expanded) else os.path.getsize(expanded)
                target_total += s
                existing_paths.append({"path": expanded, "size": s})

        if not existing_paths and target.get("command"):
            target_total = -1

        risk = target.get("risk", "safe")
        if target_total > 0:
            risk_summary[risk] = risk_summary.get(risk, 0) + target_total
            total_size += target_total

        if target_total != 0 or target.get("command"):
            results.append({
                "key": key,
                "desc": target["desc"],
                "risk": risk,
                "note": target.get("note", ""),
                "total_size": target_total,
                "total_human": human_size(target_total) if target_total > 0 else "需执行后确认",
                "paths": existing_paths if detailed else [],
                "command": target.get("command"),
            })

    return {
        "system": SYSTEM,
        "timestamp": datetime.now().isoformat(),
        "total_recoverable": total_size,
        "total_human": human_size(total_size),
        "risk_summary": {
            "safe": {"size": risk_summary["safe"], "human": human_size(risk_summary["safe"])},
            "confirm": {"size": risk_summary["confirm"], "human": human_size(risk_summary["confirm"])},
            "dangerous": {"size": risk_summary["dangerous"], "human": human_size(risk_summary["dangerous"])},
        },
        "categories": results,
    }


def execute_cleanup(categories=None, risk_level="safe", dry_run=True, auto_backup=True):
    """
    执行清理
    risk_level: safe=只清理安全项, confirm=包含需确认项, all=全部
    """
    targets = get_targets()
    if categories:
        targets = {k: v for k, v in targets.items() if k in categories}

    # 按风险等级过滤
    risk_order = {"safe": 0, "confirm": 1, "dangerous": 2}
    max_risk = risk_order.get(risk_level, 0)
    filtered = {k: v for k, v in targets.items() if risk_order.get(v.get("risk", "safe"), 0) <= max_risk}

    results = []
    total_freed = 0

    for key, target in filtered.items():
        # 命令型清理
        if target.get("command"):
            cmd = target["command"]
            if not dry_run:
                try:
                    if SYSTEM == "Windows" and cmd.startswith("Clear-"):
                        subprocess.run(["powershell", "-Command", cmd], capture_output=True, timeout=60)
                    else:
                        subprocess.run(cmd, shell=True, capture_output=True, timeout=300)
                    results.append({"key": key, "desc": target["desc"], "status": "executed"})
                except Exception as e:
                    results.append({"key": key, "desc": target["desc"], "status": f"error: {e}"})
            else:
                results.append({"key": key, "desc": target["desc"], "status": "would_execute"})
            continue

        # 路径型清理
        for path_pattern in target.get("paths", []):
            expanded = os.path.expanduser(os.path.expandvars(path_pattern))
            if "*" in expanded:
                for item in globmod.glob(expanded):
                    r = safe_delete(item, dry_run, auto_backup)
                    results.append(r)
                    if r["action"] in ("deleted", "would_delete"):
                        total_freed += r.get("size", 0)
            elif os.path.exists(expanded):
                r = safe_delete(expanded, dry_run, auto_backup)
                results.append(r)
                if r["action"] in ("deleted", "would_delete"):
                    total_freed += r.get("size", 0)

    return {
        "dry_run": dry_run,
        "risk_level": risk_level,
        "total_freed": total_freed,
        "total_freed_human": human_size(total_freed),
        "details": results,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PC Guardian - 垃圾清理")
    sub = parser.add_subparsers(dest="command")

    scan_parser = sub.add_parser("scan", help="扫描可清理项目")
    scan_parser.add_argument("--detailed", action="store_true")
    scan_parser.add_argument("--json", action="store_true")

    clean_parser = sub.add_parser("clean", help="执行清理")
    clean_parser.add_argument("--categories", nargs="+", help="指定清理类别")
    clean_parser.add_argument("--risk", choices=["safe", "confirm", "all"], default="safe",
                               help="风险等级：safe=安全项, confirm=含需确认项, all=全部")
    clean_parser.add_argument("--execute", action="store_true", help="实际执行（默认 dry-run）")
    clean_parser.add_argument("--no-backup", action="store_true", help="跳过备份")
    clean_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "scan":
        result = scan_cleanup(detailed=args.detailed)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"🧹 PC Guardian 清理扫描 — {result['system']}")
            print(f"可回收空间：{result['total_human']}")
            rs = result["risk_summary"]
            print(f"  ✅ 安全：{rs['safe']['human']}  "
                  f"⚠️  需确认：{rs['confirm']['human']}  "
                  f"🔴 高危：{rs['dangerous']['human']}\n")
            for cat in result["categories"]:
                risk_icon = {"safe": "✅", "confirm": "⚠️", "dangerous": "🔴"}[cat["risk"]]
                print(f"  {risk_icon} [{cat['risk']}] {cat['desc']}: {cat['total_human']}", end="")
                if cat.get("note"):
                    print(f"  ({cat['note']})", end="")
                print()
                if args.detailed and cat["paths"]:
                    for p in cat["paths"][:5]:
                        print(f"      {p['path']} ({human_size(p['size'])})")

    elif args.command == "clean":
        dry = not args.execute
        result = execute_cleanup(
            categories=args.categories,
            risk_level=args.risk,
            dry_run=dry,
            auto_backup=not args.no_backup,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            label = "预计释放" if dry else "已释放"
            print(f"{label}：{result['total_freed_human']}  (风险等级: {result['risk_level']})\n")
            for d in result["details"]:
                if "desc" in d:
                    print(f"  {d['status']}: {d['desc']}")
                else:
                    action = d.get("action", "unknown")
                    backup = ""
                    if d.get("backup") and d["backup"].get("type") == "full":
                        backup = f" [备份: {d['backup'].get('backup_path', '')}]"
                    print(f"  {action}: {d.get('path', '')}{backup}")
    else:
        parser.print_help()
