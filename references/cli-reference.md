# PC Guardian CLI 完整参考

## 清理模块

```bash
# 扫描（只读）
pc_guardian.py cleanup scan
pc_guardian.py cleanup scan --detailed    # 显示每个文件路径
pc_guardian.py cleanup scan --json       # JSON 输出

# 清理安全项（L1，直接执行）
pc_guardian.py cleanup clean

# 清理需确认项（L2，需 --execute）
pc_guardian.py cleanup clean --risk confirm --execute

# 清理全部（L3，需 --execute）
pc_guardian.py cleanup clean --risk all --execute

# 指定类别
pc_guardian.py cleanup clean --categories npm_cache pip_cache --execute

# 跳过备份
pc_guardian.py cleanup clean --execute --no-backup
```

## 网络模块

```bash
pc_guardian.py network diagnose           # 完整诊断
pc_guardian.py network optimize          # 自动优化
pc_guardian.py network flush-dns         # 刷新 DNS
```

## 文件整理模块

```bash
pc_guardian.py file scan <dir>           # 扫描统计
pc_guardian.py file suggest <dir>        # 整理建议
pc_guardian.py file organize <dir>       # 预览整理方案
pc_guardian.py file organize <dir> --execute  # 执行整理
pc_guardian.py file duplicates <dir>     # 查找重复文件
```

## 系统设置模块

```bash
pc_guardian.py settings list             # 列出可管理设置
pc_guardian.py settings get <key>        # 查看当前值
pc_guardian.py settings set <key> <val>  # 修改（自动备份）
pc_guardian.py settings restore <key>    # 恢复上次备份值
```

### macOS 可用设置

| key | 说明 | 可选值 |
|-----|------|-------|
| dock_autohide | Dock 自动隐藏 | 开/关 |
| dock_size | Dock 图标大小 | 数字（36-128） |
| show_hidden_files | 显示隐藏文件 | 开/关 |
| screenshot_location | 截图保存路径 | 路径 |
| power_sleep | 电脑睡眠时间 | 分钟（0=永不） |
| dns_servers | DNS 服务器 | IP 地址 |
| wifi_power | Wi-Fi 开关 | 开/关 |
| hostname | 电脑名称 | 字符串 |

## 备份与回档

```bash
pc_guardian.py backup list                        # 列出备份
pc_guardian.py backup backup <path>               # 手动备份
pc_guardian.py backup rollback <backup_path>      # 回档
pc_guardian.py log                                # 操作日志
```

## Skill 管理

```bash
pc_guardian.py skill scan                # 列出所有 skill
pc_guardian.py skill check               # 检查更新
pc_guardian.py skill report              # 完整报告
pc_guardian.py security audit            # 安全审计
```
