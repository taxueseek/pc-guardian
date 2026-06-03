---
name: pc-guardian
description: |
  PC 电脑管家 — 清理垃圾、优化网速、文件整理、系统设置管理、skill 更新检查、skill 安全审计。
  支持 macOS 和 Windows，兼容 Claude Code / Codex / Grok 等 Agent 环境。
  所有高风险操作先备份后执行，支持随时回档。

  Trigger on: "清理垃圾"、"系统清理"、"电脑卡了"、"清理缓存"、"磁盘清理"、"空间不够"
  "网速慢"、"网络诊断"、"优化网络"、"flush dns"、"ping 测试"
  "整理文件"、"文件归类"、"重复文件"、"大文件"、"下载文件夹太乱"
  "系统设置"、"修改 DNS"、"电源设置"、"Dock 设置"、"显示隐藏文件"
  "检查更新"、"skill 更新"、"安全扫描"、"skill 安全"、"电脑管家"、"电脑体检"
  "全面检查"、"系统优化"、"备份"、"回档"、"恢复设置"、"操作日志"

  Also trigger when: "帮我看看电脑"、"系统维护"、"电脑变慢了"、"磁盘快满了"
  "网络不好"、"文件太乱"、"哪些文件可以删"、"skill 有没有问题"

  DO NOT use when:
  - 需要专业数据恢复 → 使用专业数据恢复工具
  - 需要杀毒/反恶意软件 → 使用专业安全软件
  - 硬件故障诊断 → 联系硬件厂商
---

# PC Guardian — 电脑管家 v2.2

跨平台系统维护 skill。**先分析→建议→确认→备份→执行→可回档**。

## 操作分级

| 等级 | 类型 | 默认行为 | 示例 |
|------|------|---------|------|
| **L0 只读** | 扫描/诊断/查看 | 直接执行 | scan, diagnose, list, audit |
| **L1 低风险** | 安全清理/刷新 | 直接执行 | 清理回收站、npm 缓存、flush DNS |
| **L2 中风险** | 文件整理/需确认清理 | 需用户确认后执行 | 按类型整理文件、清理浏览器缓存 |
| **L3 高风险** | 系统设置/全量清理 | 需确认 + 自动备份 | 修改系统设置、清理所有缓存 |

## 备份原则

- L2/L3 操作前自动备份到 `~/.pc-guardian/backups/{timestamp}/`
- 系统设置修改前自动记录当前值到 `~/.pc-guardian/state/`
- 所有操作记录日志到 `~/.pc-guardian/operations.jsonl`
- 随时可回档：`pc_guardian.py backup rollback <path>` 或 `settings restore <key>`

## 意图路由

```
用户说了什么？
├── 清理/垃圾/缓存/空间不够     → cleanup scan → 交互选择 → cleanup clean
├── 网速慢/网络问题/ping        → network diagnose → network optimize
├── 文件乱/整理/归类/重复       → file scan → file suggest → file organize
├── 系统设置/DNS/电源/Dock      → settings list → settings set
├── skill 更新/版本检查         → skill scan → skill check
├── 安全扫描/skill 是否安全     → security audit
├── 全面检查/电脑体检           → all
├── 回档/恢复/撤销              → backup list → backup rollback
└── 查看操作记录                → log
```

## 命令参考

| 意图 | 命令 | 风险等级 |
|------|------|---------|
| 全面检查 | `pc_guardian.py all` | L0 |
| 扫描可清理项 | `pc_guardian.py cleanup scan` | L0 |
| 清理安全项 | `pc_guardian.py cleanup clean` | L1 |
| 清理需确认项 | `pc_guardian.py cleanup clean --risk confirm --execute` | L2 |
| 网络诊断 | `pc_guardian.py network diagnose` | L0 |
| 网络优化 | `pc_guardian.py network optimize` | L1 |
| 扫描目录 | `pc_guardian.py file scan <dir>` | L0 |
| 整理建议 | `pc_guardian.py file suggest <dir>` | L0 |
| 按类型整理 | `pc_guardian.py file organize <dir> --execute` | L2 |
| 查找重复 | `pc_guardian.py file duplicates <dir>` | L0 |
| 列出系统设置 | `pc_guardian.py settings list` | L0 |
| 修改系统设置 | `pc_guardian.py settings set <key> <value>` | L3 |
| 恢复系统设置 | `pc_guardian.py settings restore <key>` | L2 |
| 扫描所有 skill | `pc_guardian.py skill scan` | L0 |
| 检查 skill 更新 | `pc_guardian.py skill check` | L0 |
| 安全审计 | `pc_guardian.py security audit` | L0 |
| 列出备份 | `pc_guardian.py backup list` | L0 |
| 回档 | `pc_guardian.py backup rollback <path>` | L2 |
| 操作日志 | `pc_guardian.py log` | L0 |

详细命令参数见 `references/cli-reference.md`

## 安全边界

### 绝不操作
- 系统关键目录（/System, /usr, C:\Windows\System32）
- 应用本体（只清缓存不清程序）
- 用户文档（除非明确指定）
- 超过 500MB 的单个文件不备份（只记录元数据）

### 必须确认
- L2 操作：展示预览，等用户确认后执行
- L3 操作：展示预览 + 自动备份 + 等用户确认
- 所有删除操作：先展示明细，再执行

### 自动回档支持
- 文件删除 → 备份到 `~/.pc-guardian/backups/`
- 系统设置 → 备份到 `~/.pc-guardian/state/`
- 文件移动 → 记录源路径和目标路径

## 参考文档（按需读取）

| 文档 | 何时读取 |
|------|---------|
| `references/cli-reference.md` | 需要完整命令参数说明时 |
| `references/cleanup-guide.md` | 需要详细清理列表、安全边界、自定义规则时 |
| `references/network-guide.md` | 需要深入网络排障、MTU 调优时 |
| `references/security-checklist.md` | 需要了解完整风险模式定义时 |
