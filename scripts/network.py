#!/usr/bin/env python3
"""
PC Guardian - 网速优化模块
支持 macOS 和 Windows
"""

import os
import sys
import subprocess
import platform
import json
import socket
import time
from datetime import datetime

SYSTEM = platform.system()


def run_cmd(cmd, timeout=30):
    """执行命令并返回输出"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


# ── 网络诊断 ─────────────────────────────────────────────────────

def get_network_info():
    """获取网络基本信息"""
    info = {"system": SYSTEM, "hostname": socket.gethostname()}

    if SYSTEM == "Darwin":
        # 获取当前 Wi-Fi 信息
        r = run_cmd("/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport -I")
        if r["success"]:
            for line in r["stdout"].split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = v.strip()

        # 获取 IP
        r2 = run_cmd("ipconfig getifaddr en0")
        if r2["success"]:
            info["local_ip"] = r2["stdout"]

        # 获取默认网关
        r3 = run_cmd("netstat -nr | grep default | head -1 | awk '{print $2}'")
        if r3["success"]:
            info["gateway"] = r3["stdout"]

    elif SYSTEM == "Windows":
        r = run_cmd("ipconfig /all")
        if r["success"]:
            info["ipconfig"] = r["stdout"][:2000]

        r2 = run_cmd("powershell -Command \"Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'} | Select-Object IPAddress, InterfaceAlias | Format-List\"")
        if r2["success"]:
            info["ip_addresses"] = r2["stdout"]

    return info


def ping_test(host="8.8.8.8", count=10):
    """Ping 测试"""
    if SYSTEM == "Darwin":
        cmd = f"ping -c {count} -i 0.2 {host}"
    elif SYSTEM == "Windows":
        cmd = f"ping -n {count} {host}"
    else:
        cmd = f"ping -c {count} {host}"

    r = run_cmd(cmd, timeout=count * 2 + 10)
    if not r["success"]:
        return {"host": host, "reachable": False, "error": r["stderr"]}

    output = r["stdout"]
    result = {"host": host, "reachable": True, "raw": output}

    # 解析延迟
    if SYSTEM == "Darwin":
        # rtt min/avg/max/mdev = ...
        for line in output.split("\n"):
            if "avg" in line and "/" in line:
                parts = line.split("=")[-1].strip().split("/")
                if len(parts) >= 4:
                    result["rtt_min"] = float(parts[0])
                    result["rtt_avg"] = float(parts[1])
                    result["rtt_max"] = float(parts[2])
                    result["rtt_mdev"] = float(parts[3].split()[0])
            if "packet loss" in line:
                result["packet_loss"] = line.strip()
    elif SYSTEM == "Windows":
        for line in output.split("\n"):
            if "Average" in line:
                try:
                    avg = line.split("Average = ")[-1].replace("ms", "").strip()
                    result["rtt_avg"] = float(avg)
                except (ValueError, IndexError):
                    pass
            if "loss" in line.lower():
                result["packet_loss"] = line.strip()

    return result


def dns_test():
    """DNS 解析测试"""
    test_domains = [
        "google.com",
        "baidu.com",
        "github.com",
        "aliyun.com",
    ]
    results = []
    for domain in test_domains:
        start = time.time()
        try:
            ip = socket.gethostbyname(domain)
            elapsed = (time.time() - start) * 1000
            results.append({
                "domain": domain,
                "resolved_ip": ip,
                "latency_ms": round(elapsed, 1),
                "status": "ok",
            })
        except socket.gaierror:
            elapsed = (time.time() - start) * 1000
            results.append({
                "domain": domain,
                "resolved_ip": None,
                "latency_ms": round(elapsed, 1),
                "status": "failed",
            })
    return results


def speed_estimate():
    """简单速度估算（下载小文件）"""
    import urllib.request
    test_urls = [
        ("https://www.baidu.com/favicon.ico", "百度"),
        ("https://www.apple.com/favicon.ico", "Apple"),
    ]
    results = []
    for url, name in test_urls:
        start = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read()
            elapsed = time.time() - start
            size_kb = len(data) / 1024
            speed_kbps = (size_kb * 8) / elapsed if elapsed > 0 else 0
            results.append({
                "target": name,
                "url": url,
                "size_kb": round(size_kb, 1),
                "time_s": round(elapsed, 2),
                "speed_kbps": round(speed_kbps, 1),
                "status": "ok",
            })
        except Exception as e:
            results.append({
                "target": name,
                "url": url,
                "status": "failed",
                "error": str(e),
            })
    return results


def full_diagnostic():
    """完整网络诊断"""
    print(" 网络诊断中...\n")

    # 1. 网络信息
    info = get_network_info()
    print(" 网络信息：")
    if "local_ip" in info:
        print(f"  本地 IP: {info['local_ip']}")
    if "gateway" in info:
        print(f"  网关: {info['gateway']}")
    if "SSID" in info:
        print(f"  Wi-Fi SSID: {info.get('SSID', 'N/A')}")
    if "BSSID" in info:
        print(f"  BSSID: {info['BSSID']}")
    if "channel" in info:
        print(f"  信道: {info['channel']}")
    if "lastTxRate" in info:
        print(f"  发送速率: {info['lastTxRate']} Mbps")
    if "agrCtlRSSI" in info:
        rssi = int(info["agrCtlRSSI"])
        quality = "优" if rssi > -50 else "良" if rssi > -65 else "中" if rssi > -75 else "差"
        print(f"  信号强度: {rssi} dBm ({quality})")
    print()

    # 2. Ping 测试
    print(" Ping 测试：")
    for host in ["8.8.8.8", "114.114.114.114", "baidu.com"]:
        r = ping_test(host, count=5)
        if r["reachable"]:
            avg = r.get("rtt_avg", "?")
            loss = r.get("packet_loss", "")
            status = "[OK]" if avg != "?" and avg < 100 else "[WARN]" if avg != "?" and avg < 300 else "[FAIL]"
            print(f"  {status} {host}: avg={avg}ms  {loss}")
        else:
            print(f"  [FAIL] {host}: 不可达")
    print()

    # 3. DNS 测试
    print(" DNS 解析：")
    dns_results = dns_test()
    for d in dns_results:
        if d["status"] == "ok":
            print(f"  [OK] {d['domain']} → {d['resolved_ip']} ({d['latency_ms']}ms)")
        else:
            print(f"  [FAIL] {d['domain']}: 解析失败")
    print()

    # 4. 速度估算
    print(" 连接速度估算：")
    speed_results = speed_estimate()
    for s in speed_results:
        if s["status"] == "ok":
            print(f"  {s['target']}: {s['speed_kbps']} kbps ({s['time_s']}s)")
        else:
            print(f"  {s['target']}: 测试失败")
    print()


# ── 网络优化 ─────────────────────────────────────────────────────

def flush_dns():
    """刷新 DNS 缓存"""
    if SYSTEM == "Darwin":
        cmds = [
            "sudo dscacheutil -flushcache",
            "sudo killall -HUP mDNSResponder",
        ]
    elif SYSTEM == "Windows":
        cmds = ["ipconfig /flushdns"]
    else:
        cmds = ["sudo systemd-resolve --flush-caches"]

    results = []
    for cmd in cmds:
        r = run_cmd(cmd)
        results.append({"cmd": cmd, "success": r["success"]})
    return results


def reset_network_stack():
    """重置网络栈（温和模式）"""
    if SYSTEM == "Darwin":
        cmds = [
            # 关闭再开启 Wi-Fi（不丢其他网络配置）,
            "networksetup -setairportpower en0 off",
            "sleep 2",
            "networksetup -setairportpower en0 on",
        ]
    elif SYSTEM == "Windows":
        cmds = [
            "netsh winsock reset",
            "netsh int ip reset",
            "ipconfig /release",
            "ipconfig /renew",
        ]
    else:
        cmds = []

    results = []
    for cmd in cmds:
        r = run_cmd(cmd)
        results.append({"cmd": cmd, "success": r["success"]})
    return results


def optimize_mtu():
    """检测最佳 MTU"""
    target = "8.8.8.8"
    # 从 1500 往下找不分片的最大包
    for size in range(1500, 1300, -10):
        if SYSTEM == "Darwin":
            cmd = f"ping -c 1 -D -s {size} {target}"
        elif SYSTEM == "Windows":
            cmd = f"ping -n 1 -f -l {size} {target}"
        else:
            cmd = f"ping -c 1 -M do -s {size} {target}"

        r = run_cmd(cmd, timeout=5)
        if r["success"] and ("frag" not in r["stdout"].lower() and "df" not in r["stdout"].lower()):
            return {"optimal_mtu": size + 28, "payload_size": size}
    return {"optimal_mtu": 1400, "payload_size": 1372, "note": "保守值"}


def full_optimize():
    """执行全套网络优化"""
    print(" PC Guardian 网络优化\n")

    # 1. 先诊断
    full_diagnostic()

    # 2. 刷新 DNS
    print(" 刷新 DNS 缓存...")
    dns_results = flush_dns()
    for r in dns_results:
        mark = "[OK]" if r["success"] else "[WARN]"
        print(f"  {mark} {r['cmd']}")
    print()

    # 3. MTU 检测
    print(" MTU 检测...")
    mtu = optimize_mtu()
    print(f"  建议 MTU: {mtu['optimal_mtu']}")
    print()

    # 4. 优化建议
    print(" 优化建议：")
    print("  1. DNS 已刷新，解析问题应已解决")
    print("  2. 如果 Wi-Fi 信号弱，尝试靠近路由器或切换 5GHz 频段")
    print("  3. 如果延迟高，检查是否有后台下载占用带宽")
    print("  4. 考虑使用 1.1.1.1 或 8.8.8.8 作为备用 DNS")
    print("  5. 重启路由器可解决大部分临时网络问题")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PC Guardian - 网络优化")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("diagnose", help="网络诊断")
    sub.add_parser("optimize", help="执行优化")
    sub.add_parser("flush-dns", help="刷新 DNS 缓存")
    sub.add_parser("ping", help="Ping 测试")

    ping_parser = sub.add_parser("ping", help="Ping 测试")
    ping_parser.add_argument("--host", default="8.8.8.8")
    ping_parser.add_argument("--count", type=int, default=10)

    args = parser.parse_args()

    if args.command == "diagnose":
        full_diagnostic()
    elif args.command == "optimize":
        full_optimize()
    elif args.command == "flush-dns":
        results = flush_dns()
        for r in results:
            mark = "[OK]" if r["success"] else "[WARN]"
            print(f"{mark} {r['cmd']}")
    elif args.command == "ping":
        r = ping_test(args.host, args.count)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        parser.print_help()
