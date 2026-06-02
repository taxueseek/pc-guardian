#!/usr/bin/env python3
"""
PC Guardian - Skill 安全性核查模块
检查已安装 skill 的安全风险
"""

import os
import sys
import re
import json
from pathlib import Path
from datetime import datetime

SKILL_DIRS = [
    os.path.expanduser("~/.agents/skills"),
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.grok/skills"),
]

# ── 危险模式定义 ─────────────────────────────────────────────────

DANGEROUS_PATTERNS = {
    "数据外泄": {
        "severity": "高危",
        "patterns": [
            r"curl\s+.*POST.*http",
            r"wget\s+.*http",
            r"fetch\s*\(\s*['\"]https?://",
            r"requests\.(post|put)\s*\(",
            r"urllib\.request\.urlopen\s*\(",
            r"XMLHttpRequest",
            r"navigator\.sendBeacon",
        ],
        "desc": "向外部服务器发送数据",
    },
    "凭证窃取": {
        "severity": "高危",
        "patterns": [
            r"\.(ssh|gnupg|pem)\b",
            r"id_rsa",
            r"\.env\b",
            r"credentials?",
            r"(?:API|api)[_-]?(?:KEY|key)\b",
            r"(?:SECRET|secret)[_-]?(?:KEY|key)\b",
            r"(?:ACCESS|access)[_-]?(?:TOKEN|token)\b",
            r"(?:PRIVATE|private)[_-]?(?:KEY|key)\b",
            r"\.aws/",
            r"\.docker/config\.json",
            r"(?:password|passwd|pwd)\s*[=:]",
            r"(?:cookie|session)[_-]?(?:path|dir|token)\b",
        ],
        "desc": "访问敏感凭证文件",
    },
    "系统破坏": {
        "severity": "高危",
        "patterns": [
            r"rm\s+-rf\s+/[^*\s]",  # rm -rf / 或 rm -rf /path
            r"rm\s+-rf\s+~",
            r"format\s+[A-Z]:",
            r"del\s+/s\s+/q\s+C:\\",
            r"shutil\.rmtree\s*\(\s*['\"]/",
            r"os\.remove\s*\(\s*['\"]/",
            r"sudo\s+rm",
            r"mkfs\.",
            r"dd\s+if=.*of=/dev/",
        ],
        "desc": "危险的文件删除操作",
    },
    "权限提升": {
        "severity": "高危",
        "patterns": [
            r"sudo\s+",
            r"chmod\s+777",
            r"chmod\s+\+s",
            r"chown\s+root",
            r"setuid",
            r"setgid",
            r"pkexec",
            r"doas",
        ],
        "desc": "尝试提升权限",
    },
    "代码执行": {
        "severity": "中危",
        "patterns": [
            r"eval\s*\(",
            r"exec\s*\(",
            r"subprocess\..*shell\s*=\s*True",
            r"os\.system\s*\(",
            r"os\.popen\s*\(",
            r"child_process",
            r"vm\.runInNewContext",
            r"Function\s*\(\s*['\"]",
            r"__import__\s*\(",
            r"compile\s*\(",
        ],
        "desc": "动态代码执行",
    },
    "网络扫描": {
        "severity": "中危",
        "patterns": [
            r"nmap",
            r"masscan",
            r"socket\s*\(\s*.*SOCK_STREAM",
            r"port\s*scan",
            r"syn\s*scan",
        ],
        "desc": "网络扫描行为",
    },
    "混淆代码": {
        "severity": "中危",
        "patterns": [
            r"base64\.(encode|decode)",
            r"atob\s*\(",
            r"btoa\s*\(",
            r"String\.fromCharCode",
            r"unescape\s*\(",
            r"decodeURIComponent\s*\(",
        ],
        "desc": "可能的代码混淆",
    },
    "环境变量读取": {
        "severity": "低危",
        "patterns": [
            r"os\.environ",
            r"process\.env",
            r"getenv\s*\(",
            r"\$HOME",
            r"%USERPROFILE%",
        ],
        "desc": "读取环境变量",
    },
    "文件遍历": {
        "severity": "低危",
        "patterns": [
            r"os\.walk\s*\(\s*['\"]/",
            r"glob\.glob\s*\(\s*['\"]/",
            r"Path\s*\(\s*['\"]/\s*\)\.rglob",
        ],
        "desc": "遍历文件系统",
    },
}

# ── 白名单（合法使用场景） ──────────────────────────────────────

WHITELIST = {
    "os.environ": ["读取配置", "获取路径"],
    "subprocess": ["CLI 工具调用", "系统命令"],
    "os.walk": ["本地文件操作", "项目扫描"],
    "base64": ["数据编码", "API 请求"],
}


def scan_file(filepath):
    """扫描单个文件的安全问题"""
    findings = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            lines = content.split("\n")

        # 判断文件类型
        is_doc = filepath.endswith((".md", ".txt", ".org"))

        for category, rule in DANGEROUS_PATTERNS.items():
            for pattern in rule["patterns"]:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        stripped = line.strip()

                        # 跳过注释行
                        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
                            continue

                        # 跳过 Markdown 引用块（说明文档中引用代码示例）
                        if stripped.startswith(">"):
                            continue

                        # 文档文件（.md/.txt/.org）中的匹配大幅降权：
                        # 仅在代码围栏 ``` 内的行才视为有效匹配
                        if is_doc:
                            # 检查当前行是否在代码围栏内
                            in_code_block = False
                            for prev_line in lines[:i]:
                                if prev_line.strip().startswith("```"):
                                    in_code_block = not in_code_block
                            if not in_code_block:
                                continue

                        # 跳过纯描述性内容（行内没有实际代码）
                        # 如果匹配仅出现在引号字符串内且没有赋值/调用，跳过
                        match = re.search(pattern, line, re.IGNORECASE)
                        if match:
                            before = line[:match.start()].strip()
                            after = line[match.end():].strip()
                            # 形如 "xxx": "..." 或 | xxx | 表格描述
                            if (before.endswith('"') or before.endswith("'") or before.endswith("|")) and \
                               (after.startswith('"') or after.startswith("'") or after.startswith("|")):
                                continue

                        findings.append({
                            "category": category,
                            "severity": rule["severity"],
                            "pattern": pattern,
                            "line": i,
                            "content": stripped[:120],
                            "description": rule["desc"],
                        })
    except (PermissionError, OSError):
        pass
    return findings


def scan_skill(skill_path, exclude_self=True):
    """扫描整个 skill 目录"""
    all_findings = []
    files_scanned = 0
    risky_files = set()
    skill_name = os.path.basename(skill_path)

    for root, dirs, files in os.walk(skill_path):
        # 跳过 .git 和 node_modules
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__")]

        # 自排除：安全扫描自身时，跳过 scripts/ 中的检测规则定义文件
        if exclude_self and skill_name == "pc-guardian":
            files = [f for f in files if f != "skill_security.py"]

        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".py", ".sh", ".js", ".ts", ".md", ".json", ".yaml", ".yml", ".bat", ".ps1", ".cmd"):
                filepath = os.path.join(root, fname)
                findings = scan_file(filepath)
                files_scanned += 1
                if findings:
                    risky_files.add(filepath)
                    all_findings.extend(findings)

    # 去重（同一文件同一类别只报一次）
    seen = set()
    deduped = []
    for f in all_findings:
        key = (f["category"], f["pattern"], f.get("line"), f.get("content"))
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    # 计算风险评分
    severity_scores = {"高危": 10, "中危": 5, "低危": 1}
    risk_score = sum(severity_scores.get(f["severity"], 0) for f in deduped)

    return {
        "skill_path": skill_path,
        "skill_name": os.path.basename(skill_path),
        "files_scanned": files_scanned,
        "risky_files": len(risky_files),
        "findings": deduped,
        "risk_score": risk_score,
        "risk_level": "🔴 高风险" if risk_score >= 20 else "🟡 中风险" if risk_score >= 5 else "🟢 低风险",
    }


def check_skill_integrity(skill_path):
    """检查 skill 完整性"""
    issues = []

    skill_md = os.path.join(skill_path, "SKILL.md")
    if not os.path.exists(skill_md):
        issues.append("缺少 SKILL.md")
        return issues  # 没有 SKILL.md 则跳过后续检查

    with open(skill_md, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read(3000)

    # 检查必要字段
    if "name:" not in content:
        issues.append("SKILL.md 缺少 name 字段")
    if "description:" not in content:
        issues.append("SKILL.md 缺少 description 字段")

    # 检查断链的 references
    ref_pattern = r'references/[^ )\]"\']+'
    for match in re.finditer(ref_pattern, content):
        ref_path = match.group()
        full_ref = os.path.join(skill_path, ref_path)
        if not os.path.exists(full_ref):
            issues.append(f"断链引用: {ref_path}")

    # 检查 scripts 中的路径一致性
    scripts_dir = os.path.join(skill_path, "scripts")
    if os.path.isdir(scripts_dir):
        for f in os.listdir(scripts_dir):
            if f.endswith((".py", ".sh")):
                fpath = os.path.join(scripts_dir, f)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as sf:
                    script_content = sf.read()
                # 检查硬编码路径
                for line in script_content.split("\n"):
                    if re.search(r'~/.(agents|claude|grok)', line) and not line.strip().startswith("#"):
                        issues.append(f"脚本硬编码路径: {f}:{line.strip()[:60]}")
                        break

    return issues


def full_security_audit():
    """完整安全审计"""
    print("🔒 PC Guardian Skill 安全审计\n")

    all_skills = []
    seen = set()
    # 排除的目录：备份、归档、非 skill 目录
    EXCLUDE_DIRS = {"_archive", "_backup_20260601_102142", "_backup_zaoren_original_20260530", "ai-checker"}
    for skill_dir in SKILL_DIRS:
        if not os.path.isdir(skill_dir):
            continue
        for entry in sorted(os.listdir(skill_dir)):
            if entry in EXCLUDE_DIRS or entry.startswith("."):
                continue
            full_path = os.path.join(skill_dir, entry)
            if os.path.isdir(full_path) and entry not in seen:
                seen.add(entry)
                all_skills.append(full_path)

    print(f"扫描 {len(all_skills)} 个 skill...\n")

    results = []
    high_risk = []
    medium_risk = []
    clean = []

    for skill_path in all_skills:
        result = scan_skill(skill_path)
        integrity_issues = check_skill_integrity(skill_path)
        result["integrity_issues"] = integrity_issues
        results.append(result)

        if result["risk_score"] >= 20:
            high_risk.append(result)
        elif result["risk_score"] >= 5:
            medium_risk.append(result)
        else:
            clean.append(result)

    # 输出报告
    print(f"📊 安全概览：")
    print(f"  🔴 高风险：{len(high_risk)}")
    print(f"  🟡 中风险：{len(medium_risk)}")
    print(f"  🟢 低风险：{len(clean)}\n")

    if high_risk:
        print("=" * 60)
        print("🔴 高风险 skill（需立即审查）：")
        for r in high_risk:
            print(f"\n  📌 {r['skill_name']} (风险分: {r['risk_score']})")
            print(f"     扫描文件: {r['files_scanned']}, 风险文件: {r['risky_files']}")
            for f in r["findings"][:5]:
                print(f"     [{f['severity']}] {f['category']}: 第{f['line']}行")
                print(f"       {f['content']}")
            if len(r["findings"]) > 5:
                print(f"     ... 还有 {len(r['findings']) - 5} 个发现")
            if r["integrity_issues"]:
                print(f"     完整性问题:")
                for issue in r["integrity_issues"][:3]:
                    print(f"       ⚠️ {issue}")

    if medium_risk:
        print("\n" + "=" * 60)
        print("🟡 中风险 skill（建议关注）：")
        for r in medium_risk:
            categories = set(f["category"] for f in r["findings"])
            print(f"  📌 {r['skill_name']}: {', '.join(categories)}")

    # 完整性问题汇总
    integrity_problems = [(r["skill_name"], r["integrity_issues"]) for r in results if r["integrity_issues"]]
    if integrity_problems:
        print("\n" + "=" * 60)
        print("⚠️  完整性问题：")
        for name, issues in integrity_problems[:10]:
            for issue in issues[:2]:
                print(f"  {name}: {issue}")

    print(f"\n✅ 审计完成：{len(all_skills)} 个 skill 已扫描")
    print(f"   总发现：{sum(len(r['findings']) for r in results)} 个安全问题")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PC Guardian - Skill 安全核查")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("audit", help="完整安全审计")

    scan_parser = sub.add_parser("scan", help="扫描指定 skill")
    scan_parser.add_argument("skill_path", help="skill 路径")
    scan_parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.command == "audit":
        full_security_audit()
    elif args.command == "scan":
        result = scan_skill(args.skill_path)
        integrity = check_skill_integrity(args.skill_path)
        result["integrity_issues"] = integrity
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"🔒 {result['skill_name']} 安全扫描")
            print(f"风险等级：{result['risk_level']}")
            print(f"扫描文件：{result['files_scanned']}")
            print(f"发现问题：{len(result['findings'])}\n")
            for f in result["findings"]:
                print(f"  [{f['severity']}] L{f['line']} {f['category']}: {f['content']}")
            if integrity:
                print(f"\n完整性问题：")
                for issue in integrity:
                    print(f"  ⚠️ {issue}")
    else:
        parser.print_help()
