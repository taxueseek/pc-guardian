#!/usr/bin/env python3
"""
PC Guardian - Skill 更新检查模块
检查已安装 skill 的版本更新
"""

import os
import sys
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime

SKILL_DIRS = [
    os.path.expanduser("~/.agents/skills"),
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.grok/skills"),
]


def get_skill_version(skill_path):
    """从 SKILL.md 中提取版本信息"""
    skill_md = os.path.join(skill_path, "SKILL.md")
    if not os.path.exists(skill_md):
        return None

    try:
        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read(2000)  # 只读前 2000 字符

        # 提取 name
        name_match = re.search(r'^name:\s*(.+)', content, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else os.path.basename(skill_path)

        # 提取 version
        ver_match = re.search(r'^version:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
        version = ver_match.group(1).strip() if ver_match else "未标注"

        # 提取 description（第一行）
        desc_match = re.search(r'^description:\s*\|?\s*\n?\s*(.+)', content, re.MULTILINE)
        if not desc_match:
            desc_match = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
        description = desc_match.group(1).strip()[:80] if desc_match else ""

        # 检查是否有 git 信息
        git_dir = os.path.join(skill_path, ".git")
        has_git = os.path.isdir(git_dir)

        # 最后修改时间
        mtime = os.path.getmtime(skill_md)
        last_modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

        # 文件数量
        file_count = sum(1 for _ in Path(skill_path).rglob("*") if _.is_file())

        return {
            "name": name,
            "path": skill_path,
            "version": version,
            "description": description,
            "has_git": has_git,
            "last_modified": last_modified,
            "file_count": file_count,
        }
    except Exception as e:
        return {
            "name": os.path.basename(skill_path),
            "path": skill_path,
            "version": "读取失败",
            "error": str(e),
        }


def scan_all_skills():
    """扫描所有 skill 目录"""
    all_skills = []
    seen_names = set()

    for skill_dir in SKILL_DIRS:
        if not os.path.isdir(skill_dir):
            continue
        for entry in sorted(os.listdir(skill_dir)):
            full_path = os.path.join(skill_dir, entry)
            if os.path.isdir(full_path) and not entry.startswith("."):
                info = get_skill_version(full_path)
                if info:
                    # 去重（同名 skill 只保留一个）
                    key = info["name"]
                    if key not in seen_names:
                        seen_names.add(key)
                        all_skills.append(info)

    return all_skills


def check_skill_update(skill_path):
    """检查单个 skill 是否有 git 更新"""
    git_dir = os.path.join(skill_path, ".git")
    if not os.path.isdir(git_dir):
        return {"path": skill_path, "updatable": False, "reason": "非 git 仓库"}

    try:
        # 获取当前分支和 commit
        r = subprocess.run(
            ["git", "-C", skill_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        branch = r.stdout.strip() if r.returncode == 0 else "unknown"

        r2 = subprocess.run(
            ["git", "-C", skill_path, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        local_commit = r2.stdout.strip() if r2.returncode == 0 else "unknown"

        # 尝试 fetch（不超时太久）
        subprocess.run(
            ["git", "-C", skill_path, "fetch", "--quiet"],
            capture_output=True, timeout=30
        )

        r3 = subprocess.run(
            ["git", "-C", skill_path, "rev-parse", "--short", f"origin/{branch}"],
            capture_output=True, text=True, timeout=10
        )
        remote_commit = r3.stdout.strip() if r3.returncode == 0 else local_commit

        # 比较差异
        r4 = subprocess.run(
            ["git", "-C", skill_path, "log", f"HEAD..origin/{branch}", "--oneline"],
            capture_output=True, text=True, timeout=10
        )
        ahead_commits = r4.stdout.strip().split("\n") if r4.returncode == 0 and r4.stdout.strip() else []

        return {
            "path": skill_path,
            "updatable": True,
            "branch": branch,
            "local_commit": local_commit,
            "remote_commit": remote_commit,
            "behind_count": len(ahead_commits),
            "behind_commits": ahead_commits[:10],
            "status": "有更新" if ahead_commits else "已是最新",
        }
    except subprocess.TimeoutExpired:
        return {"path": skill_path, "updatable": True, "status": "检查超时"}
    except Exception as e:
        return {"path": skill_path, "updatable": False, "reason": str(e)}


def check_all_updates():
    """检查所有可更新 skill"""
    all_skills = scan_all_skills()
    updatable = [s for s in all_skills if s.get("has_git")]

    results = []
    for skill in updatable:
        update_info = check_skill_update(skill["path"])
        results.append(update_info)

    return results


def full_report():
    """生成完整报告"""
    print(" PC Guardian Skill 更新检查\n")

    all_skills = scan_all_skills()
    print(f"已安装 skill 总数：{len(all_skills)}\n")

    # 按版本状态分类
    versioned = [s for s in all_skills if s["version"] not in ("未标注", "读取失败")]
    unversioned = [s for s in all_skills if s["version"] == "未标注"]
    failed = [s for s in all_skills if s["version"] == "读取失败"]

    print(f" 版本统计：")
    print(f"  有版本号：{len(versioned)}")
    print(f"  无版本号：{len(unversioned)}")
    print(f"  读取失败：{len(failed)}\n")

    # Git 可更新的
    git_skills = [s for s in all_skills if s.get("has_git")]
    print(f" Git 管理：{len(git_skills)} 个\n")

    if git_skills:
        print(" 检查更新中...\n")
        updates = check_all_updates()
        has_update = [u for u in updates if u.get("behind_count", 0) > 0]
        up_to_date = [u for u in updates if u.get("behind_count", 0) == 0 and u.get("updatable")]

        if has_update:
            print(f"[UP]  有 {len(has_update)} 个 skill 可更新：")
            for u in has_update:
                name = os.path.basename(u["path"])
                count = u["behind_count"]
                print(f"   {name}: 落后 {count} 个提交")
                for c in u.get("behind_commits", [])[:3]:
                    print(f"      {c}")
                print()
        else:
            print("[OK] 所有 git 管理的 skill 均为最新\n")

    # 未版本化的 skill 提醒
    if unversioned:
        print(f"[WARN]  {len(unversioned)} 个 skill 未标注版本（建议添加 version 字段）：")
        for s in unversioned[:10]:
            print(f"  - {s['name']}")
        if len(unversioned) > 10:
            print(f"  ... 还有 {len(unversioned) - 10} 个")
        print()

    # 最近修改
    print(" 最近修改的 skill：")
    sorted_skills = sorted(all_skills, key=lambda x: x.get("last_modified", ""), reverse=True)
    for s in sorted_skills[:5]:
        print(f"  {s['last_modified']}  {s['name']}  v{s['version']}")
    print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PC Guardian - Skill 更新检查")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scan", help="扫描所有 skill")
    sub.add_parser("check", help="检查更新")
    sub.add_parser("report", help="完整报告")

    scan_parser = sub.add_parser("list", help="列出所有 skill")
    scan_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "scan" or args.command == "list":
        skills = scan_all_skills()
        if args.json:
            print(json.dumps(skills, ensure_ascii=False, indent=2))
        else:
            for s in skills:
                git_mark = "" if s.get("has_git") else "  "
                print(f"  {git_mark} {s['name']:40s} v{s['version']:15s}  {s['last_modified']}")

    elif args.command == "check":
        results = check_all_updates()
        for r in results:
            name = os.path.basename(r["path"])
            status = r.get("status", "未知")
            behind = r.get("behind_count", 0)
            mark = "[UP]" if behind > 0 else "[OK]"
            print(f"  {mark} {name}: {status} ({behind} commits behind)")

    elif args.command == "report":
        full_report()
    else:
        parser.print_help()
