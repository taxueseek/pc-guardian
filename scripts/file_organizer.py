#!/usr/bin/env python3
"""
PC Guardian - 文件整理模块
智能分析和整理文件：按类型归类、查找重复文件、清理空目录、大文件扫描

Agent 优势（vs 传统软件）：
- 语义理解：能读懂文件名含义，按项目/用途归类（不只是按扩展名）
- 智能建议：分析文件内容相关性，建议合并/拆分文件夹
- 安全可控：先分析→建议→确认→执行→可回档
"""

import os
import sys
import shutil
import json
import hashlib
import platform
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

SYSTEM = platform.system()

# ── 文件类型映射 ────────────────────────────────────────────────

FILE_CATEGORIES = {
    "图片": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff", ".raw", ".heic"},
    "视频": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg"},
    "音频": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"},
    "文档": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".rtf", ".pages", ".numbers", ".keynote"},
    "代码": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".sh", ".bat", ".ps1"},
    "压缩包": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".dmg", ".iso"},
    "安装包": {".exe", ".msi", ".pkg", ".deb", ".rpm", ".app"},
    "数据": {".csv", ".json", ".xml", ".yaml", ".yml", ".sql", ".db", ".sqlite"},
    "设计": {".psd", ".ai", ".sketch", ".fig", ".xd", ".blend", ".obj", ".fbx"},
}


def get_category(filename):
    """获取文件所属分类"""
    ext = os.path.splitext(filename)[1].lower()
    for cat, exts in FILE_CATEGORIES.items():
        if ext in exts:
            return cat
    return "其他"


def scan_directory(target_dir, recursive=True):
    """扫描目录，返回文件统计"""
    target_dir = os.path.expanduser(target_dir)
    if not os.path.isdir(target_dir):
        return None

    stats = {
        "total_files": 0,
        "total_size": 0,
        "categories": defaultdict(lambda: {"count": 0, "size": 0, "files": []}),
        "large_files": [],      # > 100MB
        "old_files": [],        # > 365天未访问
        "empty_dirs": [],
        "recent_files": [],     # 7天内修改
    }

    cutoff_old = datetime.now() - timedelta(days=365)
    cutoff_recent = datetime.now() - timedelta(days=7)
    large_threshold = 100 * 1024 * 1024  # 100MB

    walker = os.walk(target_dir) if recursive else [(target_dir, [], os.listdir(target_dir))]

    for root, dirs, files in walker:
        # 空目录检测
        if not files and not dirs:
            stats["empty_dirs"].append(root)

        for fname in files:
            filepath = os.path.join(root, fname)
            try:
                st = os.stat(filepath)
                size = st.st_size
                mtime = datetime.fromtimestamp(st.st_mtime)
                atime = datetime.fromtimestamp(st.st_atime)

                stats["total_files"] += 1
                stats["total_size"] += size

                # 分类
                cat = get_category(fname)
                stats["categories"][cat]["count"] += 1
                stats["categories"][cat]["size"] += size
                if len(stats["categories"][cat]["files"]) < 5:  # 每类只存前5个示例
                    stats["categories"][cat]["files"].append(filepath)

                # 大文件
                if size > large_threshold:
                    stats["large_files"].append({
                        "path": filepath, "size": size,
                        "mtime": mtime.strftime("%Y-%m-%d"),
                    })

                # 旧文件
                if atime < cutoff_old:
                    stats["old_files"].append({
                        "path": filepath, "size": size,
                        "last_access": atime.strftime("%Y-%m-%d"),
                    })

                # 最近文件
                if mtime > cutoff_recent:
                    stats["recent_files"].append({
                        "path": filepath, "size": size,
                        "mtime": mtime.strftime("%Y-%m-%d"),
                    })
            except (PermissionError, OSError):
                continue

    # 排序
    stats["large_files"].sort(key=lambda x: x["size"], reverse=True)
    stats["old_files"].sort(key=lambda x: x["last_access"])

    # 转换 defaultdict
    stats["categories"] = dict(stats["categories"])
    return stats


def find_duplicates(target_dir, min_size=1024):
    """查找重复文件（基于哈希）"""
    target_dir = os.path.expanduser(target_dir)
    if not os.path.isdir(target_dir):
        return []

    # 先按大小分组
    size_map = defaultdict(list)
    for root, dirs, files in os.walk(target_dir):
        for fname in files:
            filepath = os.path.join(root, fname)
            try:
                size = os.path.getsize(filepath)
                if size >= min_size:
                    size_map[size].append(filepath)
            except (PermissionError, OSError):
                continue

    # 对同大小文件计算哈希
    duplicates = []
    for size, paths in size_map.items():
        if len(paths) < 2:
            continue
        hash_map = defaultdict(list)
        for p in paths:
            try:
                h = file_hash(p)
                if h:
                    hash_map[h].append(p)
            except (PermissionError, OSError):
                continue
        for h, dup_paths in hash_map.items():
            if len(dup_paths) >= 2:
                duplicates.append({
                    "size": size,
                    "hash": h,
                    "files": dup_paths,
                })

    duplicates.sort(key=lambda x: x["size"] * len(x["files"]), reverse=True)
    return duplicates


def file_hash(filepath, algorithm="md5", chunk_size=8192):
    """计算文件哈希"""
    h = hashlib.new(algorithm)
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None


def suggest_organization(target_dir):
    """智能整理建议"""
    stats = scan_directory(target_dir)
    if not stats:
        return None

    suggestions = []

    # 1. 文件类型分散 → 建议归类
    if len(stats["categories"]) > 3 and stats["total_files"] > 20:
        suggestions.append({
            "type": "归类整理",
            "desc": f"检测到 {len(stats['categories'])} 种文件类型分散在目录中",
            "detail": {cat: f"{info['count']}个文件 / {human_size(info['size'])}"
                       for cat, info in stats["categories"].items()},
            "action": "按类型创建子文件夹并移动",
        })

    # 2. 大文件
    if stats["large_files"]:
        total_large = sum(f["size"] for f in stats["large_files"])
        suggestions.append({
            "type": "大文件",
            "desc": f"发现 {len(stats['large_files'])} 个大文件（>{human_size(100*1024*1024)}），共 {human_size(total_large)}",
            "files": [f["path"] for f in stats["large_files"][:10]],
            "action": "建议移动到外置存储或云盘",
        })

    # 3. 旧文件
    if stats["old_files"]:
        total_old = sum(f["size"] for f in stats["old_files"][:50])
        suggestions.append({
            "type": "陈旧文件",
            "desc": f"发现 {len(stats['old_files'])} 个超过1年未访问的文件",
            "files": [f["path"] for f in stats["old_files"][:10]],
            "action": "建议归档或删除",
        })

    # 4. 空目录
    if stats["empty_dirs"]:
        suggestions.append({
            "type": "空目录",
            "desc": f"发现 {len(stats['empty_dirs'])} 个空目录",
            "files": stats["empty_dirs"][:10],
            "action": "建议删除",
        })

    return suggestions


def human_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def organize_by_type(target_dir, dry_run=True):
    """按文件类型整理到子文件夹"""
    target_dir = os.path.expanduser(target_dir)
    operations = []

    for root, dirs, files in os.walk(target_dir):
        # 跳过已整理的子目录
        dirs[:] = [d for d in dirs if d not in FILE_CATEGORIES]

        for fname in files:
            filepath = os.path.join(root, fname)
            cat = get_category(fname)
            if cat == "其他":
                continue

            target_subdir = os.path.join(target_dir, cat)
            target_path = os.path.join(target_subdir, fname)

            # 处理重名
            if os.path.exists(target_path):
                base, ext = os.path.splitext(fname)
                target_path = os.path.join(target_subdir, f"{base}_dup{ext}")

            operations.append({
                "source": filepath,
                "target": target_path,
                "category": cat,
            })

    if dry_run:
        return operations

    # 实际执行
    results = []
    for op in operations:
        try:
            os.makedirs(os.path.dirname(op["target"]), exist_ok=True)
            shutil.move(op["source"], op["target"])
            results.append({**op, "status": "moved"})
        except Exception as e:
            results.append({**op, "status": f"error: {e}"})
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PC Guardian - 文件整理")
    sub = parser.add_subparsers(dest="command")

    scan_parser = sub.add_parser("scan", help="扫描目录统计")
    scan_parser.add_argument("directory", help="目标目录")
    scan_parser.add_argument("--json", action="store_true")

    suggest_parser = sub.add_parser("suggest", help="整理建议")
    suggest_parser.add_argument("directory", help="目标目录")
    suggest_parser.add_argument("--json", action="store_true")

    dup_parser = sub.add_parser("duplicates", help="查找重复文件")
    dup_parser.add_argument("directory", help="目标目录")
    dup_parser.add_argument("--min-size", type=int, default=1024, help="最小文件大小（字节）")

    org_parser = sub.add_parser("organize", help="按类型整理")
    org_parser.add_argument("directory", help="目标目录")
    org_parser.add_argument("--execute", action="store_true", help="实际执行")

    args = parser.parse_args()

    if args.command == "scan":
        stats = scan_directory(args.directory)
        if args.json:
            print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"📂 {args.directory}")
            print(f"文件总数: {stats['total_files']}")
            print(f"总大小: {human_size(stats['total_size'])}\n")
            print("分类统计:")
            for cat, info in sorted(stats["categories"].items(), key=lambda x: x[1]["size"], reverse=True):
                print(f"  {cat}: {info['count']}个 / {human_size(info['size'])}")
            if stats["large_files"]:
                print(f"\n大文件 (Top 5):")
                for f in stats["large_files"][:5]:
                    print(f"  {f['path']} ({human_size(f['size'])})")

    elif args.command == "suggest":
        suggestions = suggest_organization(args.directory)
        if args.json:
            print(json.dumps(suggestions, ensure_ascii=False, indent=2))
        else:
            print(f"💡 整理建议 ({args.directory})\n")
            for s in suggestions:
                print(f"  📌 {s['type']}: {s['desc']}")
                print(f"     建议: {s['action']}")
                if "files" in s:
                    for f in s["files"][:5]:
                        print(f"     - {f}")
                print()

    elif args.command == "duplicates":
        dups = find_duplicates(args.directory, args.min_size)
        print(f"🔍 重复文件 ({len(dups)} 组):\n")
        for d in dups[:20]:
            print(f"  {human_size(d['size'])} × {len(d['files'])}")
            for f in d["files"]:
                print(f"    {f}")
            print()

    elif args.command == "organize":
        dry = not args.execute
        ops = organize_by_type(args.directory, dry_run=dry)
        label = "预计移动" if dry else "已移动"
        print(f"{label} {len(ops)} 个文件\n")
        # 按类别分组显示
        by_cat = defaultdict(list)
        for op in ops:
            by_cat[op["category"]].append(op)
        for cat, cat_ops in by_cat.items():
            print(f"  📁 {cat}: {len(cat_ops)} 个文件")
            for op in cat_ops[:3]:
                print(f"    {op['source']} → {op['target']}")
            if len(cat_ops) > 3:
                print(f"    ... 还有 {len(cat_ops) - 3} 个")
    else:
        parser.print_help()
