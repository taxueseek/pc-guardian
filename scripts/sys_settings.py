#!/usr/bin/env python3
"""
PC Guardian - 系统设置管理模块
查看和调整系统设置，所有修改先备份当前值。

支持：
- macOS: defaults read/write, systemsetup, networksetup, pmset
- Windows: reg query/add, powercfg, netsh
"""

import os
import sys
import subprocess
import platform
import json
from datetime import datetime

SYSTEM = platform.system()
STATE_DIR = os.path.expanduser("~/.pc-guardian/state")
os.makedirs(STATE_DIR, exist_ok=True)


def run_cmd(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"success": r.returncode == 0, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def backup_setting(key, current_value, desc=""):
    """备份设置当前值"""
    setting_file = os.path.join(STATE_DIR, f"setting_{key}.json")
    history = []
    if os.path.exists(setting_file):
        with open(setting_file, "r") as f:
            history = json.load(f)
    history.append({
        "value": current_value,
        "description": desc,
        "timestamp": datetime.now().isoformat(),
    })
    with open(setting_file, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def restore_setting(key):
    """恢复到上一个备份值"""
    setting_file = os.path.join(STATE_DIR, f"setting_{key}.json")
    if not os.path.exists(setting_file):
        return False, "无备份"
    with open(setting_file, "r") as f:
        history = json.load(f)
    if len(history) < 2:
        return False, "只有一个备份，无法回退"
    prev = history[-2]  # 上一个值
    return True, prev["value"]


# ── macOS 设置 ───────────────────────────────────────────────────

MACOS_SETTINGS = {
    "dock_autohide": {
        "desc": "Dock 自动隐藏",
        "get": "defaults read com.apple.dock autohide",
        "set": "defaults write com.apple.dock autohide -bool {value}; killall Dock",
        "values": {"开": "true", "关": "false"},
        "category": "外观",
    },
    "dock_size": {
        "desc": "Dock 图标大小",
        "get": "defaults read com.apple.dock tilesize",
        "set": "defaults write com.apple.dock tilesize -int {value}; killall Dock",
        "category": "外观",
    },
    "show_hidden_files": {
        "desc": "显示隐藏文件",
        "get": "defaults read com.apple.finder AppleShowAllFiles",
        "set": "defaults write com.apple.finder AppleShowAllFiles -bool {value}; killall Finder",
        "values": {"开": "true", "关": "false"},
        "category": "Finder",
    },
    "screenshot_location": {
        "desc": "截图保存位置",
        "get": "defaults read com.apple.screencapture location",
        "set": "defaults write com.apple.screencapture location {value}",
        "category": "截图",
    },
    "power_sleep": {
        "desc": "电脑睡眠时间（分钟，0=永不）",
        "get": "pmset -g | grep ' sleep ' | awk '{print $2}'",
        "set": "sudo pmset -a sleep {value}",
        "category": "电源",
    },
    "disk_sleep": {
        "desc": "硬盘睡眠时间（分钟，0=永不）",
        "get": "pmset -g | grep ' disksleep ' | awk '{print $2}'",
        "set": "sudo pmset -a disksleep {value}",
        "category": "电源",
    },
    "hostname": {
        "desc": "电脑名称",
        "get": "scutil --get ComputerName",
        "set": "sudo scutil --set ComputerName {value}",
        "category": "系统",
    },
    "dns_servers": {
        "desc": "DNS 服务器",
        "get": "scutil --dns | grep 'nameserver\\[' | head -5 | awk '{print $3}'",
        "set": "networksetup -setdnsservers Wi-Fi {value}",
        "category": "网络",
    },
    "wifi_power": {
        "desc": "Wi-Fi 电源",
        "get": "networksetup -getairportpower en0",
        "set": "networksetup -setairportpower en0 {value}",
        "values": {"开": "on", "关": "off"},
        "category": "网络",
    },
}

# ── Windows 设置 ────────────────────────────────────────────────

WINDOWS_SETTINGS = {
    "power_plan": {
        "desc": "电源计划",
        "get": "powercfg /getactivescheme",
        "set": "powercfg /setactive {value}",
        "category": "电源",
    },
    "show_hidden_files": {
        "desc": "显示隐藏文件",
        "get": "reg query \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced\" /v Hidden",
        "set": "reg add \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced\" /v Hidden /t REG_DWORD /d {value} /f",
        "values": {"开": "1", "关": "2"},
        "category": "Explorer",
    },
    "hostname": {
        "desc": "电脑名称",
        "get": "hostname",
        "set": "wmic computersystem where name=\"%COMPUTERNAME%\" call rename name=\"{value}\"",
        "category": "系统",
    },
}


def get_settings():
    """获取当前系统的设置列表"""
    if SYSTEM == "Darwin":
        return MACOS_SETTINGS
    elif SYSTEM == "Windows":
        return WINDOWS_SETTINGS
    return {}


def list_settings():
    """列出所有可管理的设置及其当前值"""
    settings = get_settings()
    results = []
    for key, cfg in settings.items():
        r = run_cmd(cfg["get"])
        current = r["stdout"] if r["success"] else "获取失败"
        results.append({
            "key": key,
            "desc": cfg["desc"],
            "category": cfg.get("category", "其他"),
            "current": current,
        })
    return results


def get_setting(key):
    """获取单个设置的当前值"""
    settings = get_settings()
    if key not in settings:
        return None, "未知设置"
    cfg = settings[key]
    r = run_cmd(cfg["get"])
    if r["success"]:
        return r["stdout"], cfg["desc"]
    return None, r["stderr"]


def set_setting(key, value, auto_backup=True):
    """修改设置（自动备份当前值）"""
    settings = get_settings()
    if key not in settings:
        return False, "未知设置"

    cfg = settings[key]

    # 1. 备份当前值
    if auto_backup:
        current, _ = get_setting(key)
        if current:
            backup_setting(key, current, cfg["desc"])

    # 2. 转换值
    real_value = cfg.get("values", {}).get(value, value)

    # 3. 执行
    cmd = cfg["set"].format(value=real_value)
    r = run_cmd(cmd)
    if r["success"]:
        return True, f"已将 {cfg['desc']} 设置为 {value}"
    return False, r["stderr"]


def restore_last(key):
    """恢复到上一个备份值"""
    ok, prev_value = restore_setting(key)
    if not ok:
        return False, prev_value
    return set_setting(key, prev_value, auto_backup=False)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PC Guardian - 系统设置管理")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="列出所有可管理设置")

    get_parser = sub.add_parser("get", help="获取设置当前值")
    get_parser.add_argument("key", help="设置键名")

    set_parser = sub.add_parser("set", help="修改设置")
    set_parser.add_argument("key", help="设置键名")
    set_parser.add_argument("value", help="新值")
    set_parser.add_argument("--no-backup", action="store_true", help="不备份当前值")

    restore_parser = sub.add_parser("restore", help="恢复到上次备份的值")
    restore_parser.add_argument("key", help="设置键名")

    args = parser.parse_args()

    if args.command == "list":
        for s in list_settings():
            print(f"  [{s['category']}] {s['desc']}: {s['current']}")

    elif args.command == "get":
        val, desc = get_setting(args.key)
        print(f"{desc}: {val}")

    elif args.command == "set":
        ok, msg = set_setting(args.key, args.value, not args.no_backup)
        mark = "✅" if ok else "⚠️"
        print(f"{mark} {msg}")

    elif args.command == "restore":
        ok, msg = restore_last(args.key)
        mark = "✅" if ok else "⚠️"
        print(f"{mark} {msg}")
    else:
        parser.print_help()
