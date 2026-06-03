#!/usr/bin/env python3
"""
PC Guardian — 电脑管家统一 CLI 入口

操作分级：
  Level 0: 只读操作（scan/diagnose/list）— 直接执行
  Level 1: 低风险写入（clean safe / flush-dns）— 默认执行，可 --dry-run
  Level 2: 中风险写入（clean confirm / file organize）— 默认 dry-run，需 --execute
  Level 3: 高风险写入（clean all / sys-setting / skill update）— 默认 dry-run + 需确认 + 自动备份

用法：
  pc_guardian.py all                      # 一键全面检查（只读）
  pc_guardian.py cleanup scan             # 扫描可清理项
  pc_guardian.py cleanup clean            # 清理安全项（默认执行）
  pc_guardian.py cleanup clean --risk confirm --execute  # 清理需确认项
  pc_guardian.py network diagnose         # 网络诊断
  pc_guardian.py network optimize         # 网络优化（中风险，默认 dry-run）
  pc_guardian.py file scan <dir>          # 扫描目录
  pc_guardian.py file suggest <dir>       # 整理建议
  pc_guardian.py file organize <dir>      # 整理文件（中风险，默认 dry-run）
  pc_guardian.py file duplicates <dir>    # 查找重复文件
  pc_guardian.py settings list            # 列出可管理系统设置
  pc_guardian.py settings set <key> <val> # 修改设置（自动备份）
  pc_guardian.py settings restore <key>   # 恢复设置
  pc_guardian.py skill scan               # 扫描所有 skill
  pc_guardian.py skill check              # 检查更新
  pc_guardian.py security audit           # 安全审计
  pc_guardian.py backup list              # 列出备份
  pc_guardian.py backup rollback <path>   # 回档
  pc_guardian.py log                      # 查看操作日志
"""

import sys
import os
import json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

LOG_FILE = os.path.expanduser("~/.pc-guardian/operations.jsonl")


def show_log(limit=30):
    """查看操作日志"""
    # 搜索所有可能的日志文件
    log_files = [
        LOG_FILE,
        os.path.expanduser("~/.pc-guardian/operations.jsonl"),
    ]
    # 也搜索 backup 模块写入的日志
    for root, dirs, files in os.walk(os.path.expanduser("~/.pc-guardian")):
        for f in files:
            if f == "operations.jsonl":
                log_files.append(os.path.join(root, f))
    log_files = list(set(log_files))

    entries = []
    for lf in log_files:
        if not os.path.exists(lf):
            continue
        with open(lf, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line.strip())
                    if e.get("timestamp"):
                        entries.append(e)
                except json.JSONDecodeError:
                    continue

    if not entries:
        print(" 暂无操作日志")
        return

    entries.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    entries = entries[-limit:]
    print(f" 最近 {len(entries)} 条操作记录:\n")
    for e in entries:
        mark = "[OK]" if e.get("status") == "success" else "[FAIL]" if e.get("status") == "failed" else ""
        print(f"  {mark} {e['timestamp'][:19]}  {e.get('type', '?'):12s}  {e.get('action', '?'):10s}  {e.get('target', '?')}")
        if e.get("details"):
            for k, v in e["details"].items():
                if k in ("size", "error", "backup_path", "note"):
                    print(f"      {k}: {v}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    module = sys.argv[1]
    args = sys.argv[2:]

    # ── 全面检查（只读） ──────────────────────────────────────────
    if module == "all":
        from cleanup import scan_cleanup
        from network import get_network_info, ping_test
        from skill_updater import scan_all_skills
        from skill_security import scan_skill

        print("=" * 60)
        print(f"  PC Guardian 全面检查 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)

        print("\n [1/4] 垃圾清理扫描")
        cleanup = scan_cleanup()
        rs = cleanup["risk_summary"]
        print(f"  可回收: {cleanup['total_human']}  "
              f"(安全 {rs['safe']['human']} / 需确认 {rs['confirm']['human']})")
        for cat in cleanup["categories"][:5]:
            icon = {"safe": "[OK]", "confirm": "[WARN]", "dangerous": "[HIGH]"}[cat["risk"]]
            print(f"    {icon} {cat['desc']}: {cat['total_human']}")

        print("\n [2/4] 网络状态")
        info = get_network_info()
        if "local_ip" in info:
            print(f"  本地 IP: {info['local_ip']}")
        ping = ping_test("8.8.8.8", count=3)
        if ping["reachable"]:
            print(f"  Ping: {ping.get('rtt_avg', '?')}ms")
        else:
            print("  [WARN] 网络不可达")

        print("\n [3/4] Skill 状态")
        skills = scan_all_skills()
        git_count = sum(1 for s in skills if s.get("has_git"))
        print(f"  已安装: {len(skills)} | Git 管理: {git_count}")

        print("\n [4/4] 安全快检")
        high_risk_count = 0
        seen = set()
        for sd in [os.path.expanduser("~/.agents/skills"), os.path.expanduser("~/.claude/skills")]:
            if not os.path.isdir(sd):
                continue
            for entry in os.listdir(sd):
                fp = os.path.join(sd, entry)
                if os.path.isdir(fp) and not entry.startswith(".") and entry not in seen:
                    seen.add(entry)
                    r = scan_skill(fp)
                    if r["risk_score"] >= 20:
                        high_risk_count += 1
        if high_risk_count == 0:
            print("  [OK] 未发现高风险 skill")
        else:
            print(f"  [HIGH] {high_risk_count} 个高风险 skill（运行 security audit 查看详情）")

        print("\n" + "=" * 60)

    # ── 清理 ──────────────────────────────────────────────────────
    elif module == "cleanup":
        from cleanup import scan_cleanup, execute_cleanup
        sub = args[0] if args else "scan"
        if sub == "scan":
            detailed = "--detailed" in args
            result = scan_cleanup(detailed=detailed)
            if "--json" in args:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f" 清理扫描 — {result['system']} — {result['total_human']}\n")
                rs = result["risk_summary"]
                print(f"  [OK] 安全: {rs['safe']['human']}  "
                      f"[WARN]  需确认: {rs['confirm']['human']}  "
                      f"[HIGH] 高危: {rs['dangerous']['human']}\n")
                for cat in result["categories"]:
                    icon = {"safe": "[OK]", "confirm": "[WARN]", "dangerous": "[HIGH]"}[cat["risk"]]
                    note = f" ({cat['note']})" if cat.get("note") else ""
                    print(f"  {icon} {cat['desc']}: {cat['total_human']}{note}")
        elif sub == "clean":
            risk = "safe"
            execute = "--execute" in args
            categories = None
            if "--risk" in args:
                idx = args.index("--risk")
                risk = args[idx + 1] if idx + 1 < len(args) else "safe"
            if "--categories" in args:
                idx = args.index("--categories")
                categories = []
                for i in range(idx + 1, len(args)):
                    if args[i].startswith("--"):
                        break
                    categories.append(args[i])
            result = execute_cleanup(categories=categories, risk_level=risk,
                                     dry_run=not execute)
            if "--json" in args:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                label = "预计释放" if result["dry_run"] else "已释放"
                print(f"{label}: {result['total_freed_human']}")
                for d in result["details"]:
                    if "desc" in d:
                        print(f"  {d['status']}: {d['desc']}")
                    else:
                        print(f"  {d.get('action', '?')}: {d.get('path', '')}")

    # ── 网络 ──────────────────────────────────────────────────────
    elif module == "network":
        from network import full_diagnostic, full_optimize, flush_dns
        sub = args[0] if args else "diagnose"
        if sub == "optimize":
            full_optimize()
        elif sub == "flush-dns":
            results = flush_dns()
            for r in results:
                mark = "[OK]" if r["success"] else "[WARN]"
                print(f"{mark} {r['cmd']}")
        else:
            full_diagnostic()

    # ── 文件整理 ──────────────────────────────────────────────────
    elif module == "file":
        from file_organizer import scan_directory, suggest_organization, find_duplicates, organize_by_type, human_size
        sub = args[0] if args else "help"
        if sub == "scan":
            target_dir = args[1] if len(args) > 1 else "."
            stats = scan_directory(target_dir)
            if "--json" in args:
                print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
            else:
                print(f" {args[1]}: {stats['total_files']} 个文件, {human_size(stats['total_size'])}")
                for cat, info in sorted(stats["categories"].items(), key=lambda x: x[1]["size"], reverse=True):
                    print(f"  {cat}: {info['count']}个 / {human_size(info['size'])}")
        elif sub == "suggest":
            suggestions = suggest_organization(args[1])
            for s in suggestions:
                print(f"   {s['type']}: {s['desc']} → {s['action']}")
        elif sub == "duplicates":
            dups = find_duplicates(args[1])
            print(f" {len(dups)} 组重复文件:")
            for d in dups[:10]:
                print(f"  {human_size(d['size'])} × {len(d['files'])}")
                for f in d["files"]:
                    print(f"    {f}")
        elif sub == "organize":
            dry = "--execute" not in args
            ops = organize_by_type(args[1], dry_run=dry)
            label = "预计移动" if dry else "已移动"
            print(f"{label}: {len(ops)} 个文件")
        else:
            print("file scan|suggest|duplicates|organize <dir>")

    # ── 系统设置 ──────────────────────────────────────────────────
    elif module == "settings":
        from sys_settings import list_settings, get_setting, set_setting, restore_last
        sub = args[0] if args else "list"
        if sub == "list":
            for s in list_settings():
                print(f"  [{s['category']}] {s['desc']}: {s['current']}")
        elif sub == "get":
            val, desc = get_setting(args[1])
            print(f"{desc}: {val}")
        elif sub == "set":
            ok, msg = set_setting(args[1], args[2])
            print(f"{'[OK]' if ok else '[WARN]'} {msg}")
        elif sub == "restore":
            ok, msg = restore_last(args[1])
            print(f"{'[OK]' if ok else '[WARN]'} {msg}")

    # ── Skill 管理 ────────────────────────────────────────────────
    elif module == "skill":
        from skill_updater import scan_all_skills, check_all_updates, full_report
        sub = args[0] if args else "scan"
        if sub == "check":
            for r in check_all_updates():
                name = os.path.basename(r["path"])
                behind = r.get("behind_count", 0)
                mark = "[UP]" if behind > 0 else "[OK]"
                print(f"  {mark} {name}: {r.get('status', '?')} ({behind} commits)")
        elif sub == "report":
            full_report()
        else:
            for s in scan_all_skills():
                git = "" if s.get("has_git") else "  "
                print(f"  {git} {s['name']:40s} v{s['version']:15s}  {s['last_modified']}")

    # ── 安全审计 ──────────────────────────────────────────────────
    elif module == "security":
        from skill_security import full_security_audit
        full_security_audit()

    # ── 备份与回档 ────────────────────────────────────────────────
    elif module == "backup":
        from backup import backup_file_or_dir, rollback, list_backups
        sub = args[0] if args else "list"
        if sub == "backup":
            path, msg = backup_file_or_dir(args[1])
            print(msg)
        elif sub == "rollback":
            ok, msg = rollback(args[1])
            print(msg)
        elif sub == "list":
            backups = list_backups()
            for b in backups:
                print(f"  {b['timestamp'][:19]}  {b['target']}")
                if b.get("backup_path"):
                    print(f"    → {b['backup_path']}")

    # ── 操作日志 ──────────────────────────────────────────────────
    elif module == "log":
        show_log()

    else:
        print(f"未知模块: {module}")
        print("可用模块: all, cleanup, network, file, settings, skill, security, backup, log")


if __name__ == "__main__":
    main()
