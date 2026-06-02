#!/usr/bin/env python3
"""
PC Guardian — 交互式终端 UI
参考传统电脑管家界面：推荐勾选 + 可选项 + 一键执行

纯 Python 标准库实现，兼容任何终端环境。
使用 ANSI 转义码绘制界面，readchar 处理键盘输入。
"""

import os
import sys
import json
import subprocess
import shutil
import tty
import termios
import select
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ── 终端工具 ─────────────────────────────────────────────────────

def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def move_cursor(y, x):
    sys.stdout.write(f"\033[{y};{x}H")


def set_color(fg=None, bg=None, bold=False, dim=False, reverse=False):
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if reverse:
        codes.append("7")
    if fg is not None:
        if fg < 8:
            codes.append(str(30 + fg))
        else:
            codes.append(f"38;5;{fg}")
    if bg is not None:
        if bg < 8:
            codes.append(str(40 + bg))
        else:
            codes.append(f"48;5;{bg}")
    if codes:
        sys.stdout.write(f"\033[{';'.join(codes)}m")


def reset_color():
    sys.stdout.write("\033[0m")


def get_terminal_size():
    try:
        import struct, fcntl
        h, w = struct.unpack("hh", fcntl.ioctl(1, termios.TIOCGWINSZ, b"\0" * 4))
        return h, w
    except:
        return 24, 80


def read_key():
    """读取单个按键（兼容模式：优先 raw 模式，失败则用 input）"""
    fd = sys.stdin.fileno()
    try:
        old_settings = termios.tcgetattr(fd)
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        if ch == '\x1b':
            try:
                ch2 = sys.stdin.read(1)
                if ch2 == '[':
                    ch3 = sys.stdin.read(1)
                    key_map = {'A': 'UP', 'B': 'DOWN', 'C': 'RIGHT', 'D': 'LEFT'}
                    return key_map.get(ch3, ch + ch2)
            except:
                pass
            return 'ESC'
        elif ch in ('\r', '\n'):
            return 'ENTER'
        elif ch == ' ':
            return 'SPACE'
        elif ch == '\x03':
            return 'QUIT'
        return ch
    except (termios.error, OSError, IOError):
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings) if 'old_settings' in dir() else None
        try:
            line = input("").strip().lower()
            mapping = {
                'j': 'DOWN', 'k': 'UP', 'q': 'QUIT',
                ' ': 'SPACE', 'a': 'a', 'r': 'r',
                'w': 'UP', 's': 'DOWN',
                'h': 'LEFT', 'l': 'RIGHT',
                '': 'ENTER',
            }
            return mapping.get(line, line)
        except (EOFError, KeyboardInterrupt):
            return 'QUIT'


# ── 颜色常量 ─────────────────────────────────────────────────────

C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_UNDERLINE = "\033[4m"
C_REVERSE = "\033[7m"

# 前景色
C_BLACK = "\033[30m"
C_RED = "\033[31m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_CYAN = "\033[36m"
C_WHITE = "\033[37m"

# 背景色
C_BG_BLACK = "\033[40m"
C_BG_RED = "\033[41m"
C_BG_GREEN = "\033[42m"
C_BG_YELLOW = "\033[43m"
C_BG_BLUE = "\033[44m"
C_BG_MAGENTA = "\033[45m"
C_BG_CYAN = "\033[46m"
C_BG_WHITE = "\033[47m"

# 组合
C_TITLE = C_CYAN + C_BOLD
C_SELECTED = C_BLACK + C_BG_WHITE + C_BOLD
C_CHECKED = C_GREEN + C_BOLD
C_UNCHECKED = C_DIM
C_SAFE = C_GREEN
C_WARNING = C_YELLOW
C_DANGER = C_RED + C_BOLD
C_ACCENT = C_CYAN
C_BTN = C_WHITE + C_BG_BLUE
C_BTN_FOCUS = C_BLACK + C_BG_YELLOW + C_BOLD
C_DIM_COLOR = C_DIM


# ── 数据获取 ─────────────────────────────────────────────────────

def get_cleanup_data():
    """获取清理扫描数据"""
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPT_DIR, "cleanup.py"), "scan", "--json"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    return None


def get_disk_info():
    """获取磁盘使用情况"""
    total, used, free = shutil.disk_usage("/")
    return {
        "total": total,
        "used": used,
        "free": free,
        "percent": used / total * 100,
    }


def human_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


# ── 颜色主题 ─────────────────────────────────────────────────────

# ── UI 绘制函数 ─────────────────────────────────────────────────

def draw_box(y, x, h, w, title=""):
    """绘制边框"""
    horizontal = "─" * (w - 2)
    sys.stdout.write(f"\033[{y};{x}H┌{horizontal}┐")
    for i in range(1, h - 1):
        sys.stdout.write(f"\033[{y + i};{x}H│{' ' * (w - 2)}│")
    sys.stdout.write(f"\033[{y + h - 1};{x}H└{horizontal}┘")
    if title:
        sys.stdout.write(f"\033[{y};{x + 2}H {C_TITLE}{title}{C_RESET}")


def draw_progress_bar(y, x, width, percent, color_fg=C_GREEN, color_bg=C_DIM):
    """绘制进度条"""
    filled = int(width * percent / 100)
    empty = width - filled
    bar_fg = "█" * filled
    bar_bg = "░" * empty
    sys.stdout.write(f"\033[{y};{x}H{color_fg}{bar_fg}{C_RESET}{color_bg}{bar_bg}{C_RESET}")


def draw_button(y, x, label, focused=False):
    """绘制按钮"""
    btn = f" {label} "
    if focused:
        sys.stdout.write(f"\033[{y};{x}H{C_BTN_FOCUS}{btn}{C_RESET}")
    else:
        sys.stdout.write(f"\033[{y};{x}H{C_BTN}{btn}{C_RESET}")


def draw_text(y, x, text, color=C_RESET):
    """在指定位置绘制文本"""
    sys.stdout.write(f"\033[{y};{x}H{color}{text}{C_RESET}")


def draw_hline(y, x, width, color=C_DIM_COLOR):
    """绘制水平线"""
    sys.stdout.write(f"\033[{y};{x}H{color}{'─' * width}{C_RESET}")


# ── 主界面 ──────────────────────────────────────────────────────

def main_tui():
    """主交互界面"""
    # 获取数据
    clear_screen()
    sys.stdout.write(f"\033[1;1H{C_ACCENT}正在扫描系统...{C_RESET}")
    sys.stdout.flush()
    cleanup_data = get_cleanup_data()
    disk_info = get_disk_info()

    # 状态
    cursor_y = 0
    scroll_offset = 0
    current_tab = 0  # 0=清理, 1=文件, 2=网络, 3=安全
    message = ""
    message_time = 0

    # 勾选状态（默认推荐项勾选）
    checked = {}
    if cleanup_data:
        for cat in cleanup_data.get("categories", []):
            checked[cat["key"]] = (cat["risk"] == "safe")

    tabs = ["垃圾清理", "文件整理", "网络诊断", "安全中心"]
    tab_icons = ["🧹", "📂", "📡", "🔒"]

    while True:
        clear_screen()
        max_y, max_x = get_terminal_size()

        # ── 顶部标题栏 ────────────────────────────────────────
        sys.stdout.write(f"\033[1;1H{C_WHITE}{C_BG_BLUE}{' ' * max_x}{C_RESET}")
        title = "🛡️  PC Guardian 电脑管家"
        sys.stdout.write(f"\033[1;3H{C_WHITE}{C_BG_BLUE}{C_BOLD}{title}{C_RESET}")
        sys.stdout.write(f"\033[1;{max_x - 15}H{C_WHITE}{C_BG_BLUE}{datetime.now().strftime('%H:%M')}{C_RESET}")

        # ── Tab 栏 ────────────────────────────────────────────
        tab_x = 2
        for i, (icon, tab) in enumerate(zip(tab_icons, tabs)):
            label = f" {icon}{tab} "
            if i == current_tab:
                sys.stdout.write(f"\033[3;{tab_x}H{C_SELECTED}{label}{C_RESET}")
            else:
                sys.stdout.write(f"\033[3;{tab_x}H{C_DIM_COLOR}{label}{C_RESET}")
            tab_x += len(tab) + 4

        # ── 磁盘状态条 ────────────────────────────────────────
        disk_pct = disk_info["percent"]
        disk_color = C_SAFE if disk_pct < 70 else C_WARNING if disk_pct < 85 else C_DANGER
        sys.stdout.write(f"\033[5;3H{C_RESET}磁盘: ")
        draw_progress_bar(5, 10, 30, disk_pct, disk_color, C_DIM_COLOR)
        sys.stdout.write(f"\033[5;42H{disk_color}{C_BOLD} {disk_pct:.0f}% {C_RESET}")
        sys.stdout.write(f"\033[5;50H{C_DIM_COLOR}可用 {human_size(disk_info['free'])} / 总计 {human_size(disk_info['total'])}{C_RESET}")

        # ── 内容区域 ──────────────────────────────────────────
        if current_tab == 0:
            draw_cleanup_tab(cleanup_data, checked, cursor_y, scroll_offset, max_y, max_x)
        elif current_tab == 1:
            draw_file_tab(max_y, max_x)
        elif current_tab == 2:
            draw_network_tab(max_y, max_x)
        elif current_tab == 3:
            draw_security_tab(max_y, max_x)

        # ── 底部操作栏 ────────────────────────────────────────
        draw_hline(max_y - 2, 1, max_x - 2)

        if current_tab == 0 and cleanup_data:
            total_selected = sum(
                cat["total_size"] for cat in cleanup_data.get("categories", [])
                if checked.get(cat["key"], False) and cat["total_size"] > 0
            )
            sys.stdout.write(f"\033[{max_y - 1};3H{C_ACCENT}{C_BOLD}预计释放: {human_size(total_selected)}{C_RESET}")

            draw_button(max_y - 1, 25, "↑↓选择", False)
            draw_button(max_y - 1, 37, "Space勾选", False)
            draw_button(max_y - 1, 50, "A全选安全", False)
            draw_button(max_y - 1, 62, "R推荐", False)
            draw_button(max_y - 1, 70, "Enter执行", True)
            # 输入提示
            sys.stdout.write(f"\033[{max_y};1H{C_DIM_COLOR} j/k=上下 空格=勾选 a=全选 r=推荐 q=执行 Tab=切换{ C_RESET}")
        else:
            draw_button(max_y - 1, 3, "←→切换Tab", False)
            draw_button(max_y - 1, 18, "Q退出", False)

        # 消息提示
        if message and (datetime.now().timestamp() - message_time) < 3:
            sys.stdout.write(f"\033[{max_y - 1};{max_x - len(message) - 4}H{C_SAFE}{C_BOLD}{message}{C_RESET}")

        sys.stdout.flush()

        # ── 键盘处理 ──────────────────────────────────────────
        key = read_key()

        if key in ('q', 'Q', 'QUIT'):
            break

        elif key == 'LEFT':
            current_tab = (current_tab - 1) % len(tabs)
            cursor_y = 0
            scroll_offset = 0

        elif key == 'RIGHT':
            current_tab = (current_tab + 1) % len(tabs)
            cursor_y = 0
            scroll_offset = 0

        elif current_tab == 0 and cleanup_data:
            categories = cleanup_data.get("categories", [])
            visible_items = len(categories)

            if key == 'UP':
                cursor_y = max(0, cursor_y - 1)
                if cursor_y < scroll_offset:
                    scroll_offset = cursor_y

            elif key == 'DOWN':
                cursor_y = min(visible_items - 1, cursor_y + 1)
                visible_rows = max_y - 14
                if cursor_y >= scroll_offset + visible_rows:
                    scroll_offset = cursor_y - visible_rows + 1

            elif key == 'SPACE':
                if cursor_y < len(categories):
                    key_name = categories[cursor_y]["key"]
                    checked[key_name] = not checked.get(key_name, False)

            elif key in ('a', 'A'):
                for cat in categories:
                    if cat["risk"] == "safe":
                        checked[cat["key"]] = True

            elif key in ('r', 'R'):
                for cat in categories:
                    checked[cat["key"]] = (cat["risk"] == "safe")
                message = "✓ 已恢复推荐选项"
                message_time = datetime.now().timestamp()

            elif key == 'ENTER':
                selected = [cat["key"] for cat in categories if checked.get(cat["key"], False)]
                if selected:
                    has_confirm = any(
                        cat["risk"] == "confirm" for cat in categories
                        if checked.get(cat["key"], False)
                    )
                    if has_confirm:
                        # 确认对话框
                        show_confirm_dialog(max_y, max_x, selected, categories)
                        message = "✅ 清理完成！"
                        message_time = datetime.now().timestamp()
                        cleanup_data = get_cleanup_data()
                    else:
                        execute_cleanup(selected)
                        message = "✅ 清理完成！"
                        message_time = datetime.now().timestamp()
                        cleanup_data = get_cleanup_data()
                else:
                    message = "⚠️ 未选择任何项目"
                    message_time = datetime.now().timestamp()


def draw_cleanup_tab(data, checked, cursor_y, scroll_offset, max_y, max_x):
    """绘制垃圾清理标签页"""
    if not data:
        draw_text(7, 3, "扫描失败", C_DANGER)
        return

    # 主面板
    panel_x = 1
    panel_y = 6
    panel_w = max_x - 4
    panel_h = max_y - 10

    draw_box(panel_y, panel_x, panel_h, panel_w, "可清理项目")

    # 表头
    draw_text(panel_y + 2, panel_x + 3, "☑", C_DIM_COLOR)
    draw_text(panel_y + 2, panel_x + 8, "类别", C_DIM_COLOR + C_BOLD)
    draw_text(panel_y + 2, panel_x + 22, "大小", C_DIM_COLOR + C_BOLD)
    draw_text(panel_y + 2, panel_x + 32, "风险", C_DIM_COLOR + C_BOLD)
    draw_text(panel_y + 2, panel_x + 42, "说明", C_DIM_COLOR + C_BOLD)
    draw_hline(panel_y + 3, panel_x + 1, panel_w - 2)

    categories = data.get("categories", [])
    visible_rows = panel_h - 5

    for i in range(min(visible_rows, len(categories))):
        idx = i + scroll_offset
        if idx >= len(categories):
            break

        cat = categories[idx]
        row_y = panel_y + 4 + i
        is_selected = (idx == cursor_y)

        # 选中背景
        if is_selected:
            sys.stdout.write(f"\033[{row_y};{panel_x + 1}H{C_SELECTED}{' ' * (panel_w - 2)}{C_RESET}")

        # 勾选框
        is_checked = checked.get(cat["key"], False)
        check = "[✓]" if is_checked else "[ ]"
        check_color = C_CHECKED if is_checked else C_UNCHECKED
        if is_selected:
            check_color = C_SELECTED
        draw_text(row_y, panel_x + 3, check, check_color)

        # 类别名
        name = cat["desc"][:13]
        item_color = C_SELECTED if is_selected else C_RESET
        draw_text(row_y, panel_x + 8, name, item_color)

        # 大小
        size_str = cat["total_human"][:10]
        draw_text(row_y, panel_x + 22, size_str, item_color)

        # 风险标签
        risk_labels = {
            "safe": ("安全", C_SAFE),
            "confirm": ("需确认", C_WARNING),
            "dangerous": ("高危", C_DANGER),
        }
        risk_text, risk_color = risk_labels.get(cat["risk"], ("?", C_RESET))
        if is_selected:
            risk_color = C_SELECTED
        draw_text(row_y, panel_x + 32, risk_text, risk_color)

        # 说明
        note = cat.get("note", "")[:30]
        if note:
            note_color = C_DIM_COLOR if not is_selected else C_SELECTED
            draw_text(row_y, panel_x + 42, note, note_color)

    # 右侧统计面板
    stats_x = max_x // 2 + 2
    stats_y = panel_y
    stats_w = max_x // 2 - 4
    stats_h = 9

    draw_box(stats_y, stats_x, stats_h, stats_w, "清理统计")

    total = data.get("total_human", "0")
    rs = data.get("risk_summary", {})
    draw_text(stats_y + 1, stats_x + 3, "总可回收:", C_RESET)
    draw_text(stats_y + 1, stats_x + 18, total, C_ACCENT + C_BOLD)

    draw_text(stats_y + 2, stats_x + 3, "✅  安全:", C_SAFE)
    draw_text(stats_y + 2, stats_x + 18, rs.get("safe", {}).get("human", "0"), C_SAFE)

    draw_text(stats_y + 3, stats_x + 3, "⚠️  需确认:", C_WARNING)
    draw_text(stats_y + 3, stats_x + 18, rs.get("confirm", {}).get("human", "0"), C_WARNING)

    draw_text(stats_y + 4, stats_x + 3, "🔴 高危:", C_DANGER)
    draw_text(stats_y + 4, stats_x + 18, rs.get("dangerous", {}).get("human", "0"), C_DANGER)

    draw_text(stats_y + 6, stats_x + 3, "💡 推荐清理安全项", C_DIM_COLOR)
    draw_text(stats_y + 7, stats_x + 3, "   按 R 恢复推荐", C_DIM_COLOR)


def draw_file_tab(max_y, max_x):
    """绘制文件整理标签页"""
    y = 7
    draw_text(y, 3, "📂 文件整理功能", C_TITLE)
    y += 2
    items = [
        ("按类型归类", "将分散的文件按类型整理到子文件夹"),
        ("查找重复文件", "基于哈希查找重复文件，节省空间"),
        ("大文件扫描", "找出占用空间最大的文件"),
        ("旧文件清理", "清理超过30天未访问的文件"),
    ]
    for title, desc in items:
        draw_text(y, 5, f"• {title}", C_ACCENT + C_BOLD)
        draw_text(y, 25, desc, C_DIM_COLOR)
        y += 1
    y += 1
    draw_text(y, 5, "命令行操作:", C_DIM_COLOR)
    y += 1
    draw_text(y, 7, "pc_guardian.py file scan <目录>", C_ACCENT)
    y += 1
    draw_text(y, 7, "pc_guardian.py file suggest <目录>", C_ACCENT)
    y += 1
    draw_text(y, 7, "pc_guardian.py file duplicates <目录>", C_ACCENT)


def draw_network_tab(max_y, max_x):
    """绘制网络诊断标签页"""
    y = 7
    draw_text(y, 3, "📡 网络诊断功能", C_TITLE)
    y += 2
    items = [
        ("网络信息", "IP、网关、Wi-Fi 信号强度"),
        ("Ping 测试", "检测延迟和丢包"),
        ("DNS 测试", "多域名解析延迟"),
        ("速度估算", "下载速度测试"),
    ]
    for title, desc in items:
        draw_text(y, 5, f"• {title}", C_ACCENT + C_BOLD)
        draw_text(y, 25, desc, C_DIM_COLOR)
        y += 1
    y += 1
    draw_text(y, 5, "命令行操作:", C_DIM_COLOR)
    y += 1
    draw_text(y, 7, "pc_guardian.py network diagnose", C_ACCENT)
    y += 1
    draw_text(y, 7, "pc_guardian.py network optimize", C_ACCENT)


def draw_security_tab(max_y, max_x):
    """绘制安全中心标签页"""
    y = 7
    draw_text(y, 3, "🔒 安全中心", C_TITLE)
    y += 2
    items = [
        ("Skill 安全审计", "检测已安装 skill 的安全风险"),
        ("数据外泄检测", "检查是否有 skill 向外发送数据"),
        ("凭证安全", "检查是否有 skill 访问敏感凭证"),
        ("完整性检查", "检查 SKILL.md 断链和硬编码路径"),
    ]
    for title, desc in items:
        draw_text(y, 5, f"• {title}", C_ACCENT + C_BOLD)
        draw_text(y, 25, desc, C_DIM_COLOR)
        y += 1
    y += 1
    draw_text(y, 5, "命令行操作:", C_DIM_COLOR)
    y += 1
    draw_text(y, 7, "pc_guardian.py security audit", C_ACCENT)


def show_confirm_dialog(max_y, max_x, selected, categories):
    """显示确认对话框"""
    dialog_h = min(14, max_y - 4)
    dialog_w = 56
    dialog_y = (max_y - dialog_h) // 2
    dialog_x = (max_x - dialog_w) // 2

    # 绘制对话框背景
    for i in range(dialog_h):
        sys.stdout.write(f"\033[{dialog_y + i};{dialog_x}H{' ' * dialog_w}")

    draw_box(dialog_y, dialog_x, dialog_h, dialog_w, "确认清理")
    draw_text(dialog_y + 1, dialog_x + 3, "⚠️  包含需确认的清理项", C_WARNING + C_BOLD)
    draw_hline(dialog_y + 2, dialog_x + 2, dialog_w - 4)

    row = 3
    for cat in categories:
        if cat["key"] in selected and row < dialog_h - 3:
            risk_icon = "✅" if cat["risk"] == "safe" else "⚠️"
            color = C_SAFE if cat["risk"] == "safe" else C_WARNING
            draw_text(dialog_y + row, dialog_x + 4,
                      f"{risk_icon} {cat['desc']} ({cat['total_human']})", color)
            row += 1

    draw_text(dialog_y + dialog_h - 2, dialog_x + 3,
              "确认执行？(自动备份)  Y / N", C_RESET)

    sys.stdout.flush()

    while True:
        key = read_key()
        if key in ('y', 'Y'):
            execute_cleanup(selected)
            break
        elif key in ('n', 'N', 'ESC'):
            break


def execute_cleanup(selected):
    """执行清理"""
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "cleanup.py"),
        "clean",
        "--categories", *selected,
        "--execute",
    ]
    subprocess.run(cmd, capture_output=True, timeout=300)


def main():
    try:
        main_tui()
    except KeyboardInterrupt:
        pass
    finally:
        clear_screen()
        sys.stdout.write(f"{C_RESET}感谢使用 PC Guardian 👋{C_RESET}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
