#  PC Guardian AI 时代的智能电脑管家

> **不只是清理工具，是一个懂你电脑的 Agent。**

PC Guardian 是一款专为 AI Agent（Claude Code / Codex / Grok）设计的电脑管家 Skill。它能像专业管家一样分析你的系统、给出智能建议、安全执行清理——所有操作可回档，所有决策透明可控。

## 为什么需要 PC Guardian？

传统清理软件（CleanMyMac、CCleaner）是黑盒，你点了"清理"，不知道删了什么，删错了没法恢复。

PC Guardian 不一样：

| 能力 | 传统软件 | PC Guardian |
|------|---------|------------|
| 清理策略 | 固定规则 | 语义理解文件用途，智能分级 |
| 安全判断 | 黑白名单 | 上下文分析 + 风险评分 |
| 误删恢复 | 回收站（30天） | 完整备份 + 一键回档 |
| 操作透明 | 黑盒 | 完整操作日志 + 每步确认 |
| 文件整理 | 不支持 | 按项目/用途语义归类 |
| 系统设置 | 不支持 | 改前备份 + 一键恢复 |

## 功能一览

###  垃圾清理（智能分级）
- **安全项**：应用缓存、日志、npm/pip/brew 缓存 → 直接清理
- **需确认项**：浏览器缓存、下载旧文件、Docker 镜像 → 预览后确认
- **高危项**：系统缓存 → 自动备份 + 二次确认

###  文件整理
- 按类型归类（不只是扩展名，能理解文件用途）
- 查找重复文件（基于哈希）
- 大文件扫描 + 旧文件清理

###  网络诊断
- Ping 延迟/丢包测试
- DNS 解析速度
- 连接速度估算
- DNS 刷新、MTU 优化

### ⚙️ 系统设置管理
- macOS: Dock、Finder、电源、DNS、Wi-Fi
- Windows: 电源计划、显示设置
- 修改前自动备份，一键恢复

###  Skill 安全审计
- 检测已安装 skill 的安全风险
- 数据外泄、凭证窃取、系统破坏等 9 大类别
- 完整性检查（断链引用、硬编码路径）

##  安装

### 方式一：Claude Code / Codex 安装

```bash
# 克隆到 skill 目录
git clone https://github.com/taxueseek/pc-guardian.git \
  ~/.agents/skills/pc-guardian

# 或软链接（推荐，方便更新）
ln -s /path/to/pc-guardian ~/.agents/skills/pc-guardian
```

### 方式二：Grok 安装

```bash
cp -r pc-guardian ~/.grok/skills/pc-guardian
```

### 验证安装

```bash
python3 ~/.agents/skills/pc-guardian/scripts/pc_guardian.py all
```

##  使用方式

### 在 Agent 中直接使用

对 Claude Code / Grok 说：

- "帮我清理一下电脑"
- "磁盘快满了，看看能清理什么"
- "网速慢，诊断一下"
- "整理一下下载文件夹"
- "检查一下已安装的 skill 是否安全"

Agent 会自动调用 PC Guardian 完成操作。

### 命令行使用

```bash
# 快速全面检查
pc_guardian.py all

# 扫描可清理项
pc_guardian.py cleanup scan

# 清理安全项（直接执行）
pc_guardian.py cleanup clean

# 清理需确认项（先预览）
pc_guardian.py cleanup clean --risk confirm --execute

# 文件整理
pc_guardian.py file scan ~/Downloads
pc_guardian.py file suggest ~/Downloads
pc_guardian.py file duplicates ~/Downloads

# 网络诊断
pc_guardian.py network diagnose

# 系统设置
pc_guardian.py settings list
pc_guardian.py settings set dock_autohide 开

# 安全审计
pc_guardian.py security audit

# 查看操作日志
pc_guardian.py log

# 回档
pc_guardian.py backup list
pc_guardian.py backup rollback ~/.pc-guardian/backups/20260602-120000/
```

##  安全设计

### 操作分级

| 等级 | 类型 | 行为 |
|------|------|------|
| **L0** | 只读（扫描/诊断） | 直接执行 |
| **L1** | 低风险（安全清理） | 直接执行 |
| **L2** | 中风险（需确认清理） | 预览 → 确认 → 备份 → 执行 |
| **L3** | 高风险（系统设置） | 预览 → 确认 → 备份 → 执行 → 可回档 |

### 备份机制

```
~/.pc-guardian/
├── backups/           # 文件备份
│   └── 20260602-120000/
│       ├── Caches.bak/
│       └── Downloads.bak/
├── state/             # 系统设置备份
│   ├── dock_autohide.json
│   └── dns_servers.json
└── operations.jsonl   # 操作日志
```

### 回档命令

```bash
# 文件回档
pc_guardian.py backup rollback ~/.pc-guardian/backups/20260602-120000/Caches.bak

# 设置回档
pc_guardian.py settings restore dock_autohide
```

##  项目结构

```
pc-guardian/
├── SKILL.md                    # Skill 主入口（Agent 读取）
├── scripts/
│   ├── pc_guardian.py          # 统一 CLI 入口
│   ├── cleanup.py              # 垃圾清理（风险分级 + 自动备份）
│   ├── network.py              # 网络诊断 + 优化
│   ├── file_organizer.py       # 文件整理（扫描/建议/归类/查重）
│   ├── sys_settings.py         # 系统设置管理
│   ├── skill_updater.py        # Skill 更新检查
│   ├── skill_security.py       # Skill 安全审计
│   └── backup.py               # 备份与回档
└── references/
    ├── cli-reference.md        # 完整命令参考
    ├── cleanup-guide.md        # 清理详细指南
    ├── network-guide.md        # 网络优化指南
    └── security-checklist.md   # 安全检查清单
```

## 🖥️ 系统支持

| 功能 | macOS | Windows |
|------|-------|---------|
| 垃圾清理 | ✅ | ✅ |
| 文件整理 | ✅ | ✅ |
| 网络诊断 | ✅ | ✅ |
| 系统设置 | ✅ | ✅ |
| Skill 审计 | ✅ | ✅ |
| 安全审计 | ✅ | ✅ |

## 🤝 贡献

欢迎提交 Issue 和 PR！

## 📄 许可证

MIT License

---

*Built with ❤️ for the AI Agent era.*
