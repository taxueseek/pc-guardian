# 清理详细指南

## 安全边界

### [OK] 安全可清理
- 用户级缓存（~/Library/Caches, %TEMP%）
- 应用日志（~/Library/Logs）
- 回收站（~/.Trash, Recycle Bin）
- 包管理器缓存（npm, pip, brew）
- Xcode DerivedData / Archives
- Docker 悬空镜像（docker system prune）

### [WARN] 需谨慎
- /tmp 目录（可能含正在使用的临时文件）
- 浏览器缓存（会清除登录状态）
- Windows Prefetch（清理后首次启动变慢）

### [FAIL] 不清理
- 系统关键目录（/System, /usr, C:\Windows\System32）
- 应用本体（只清缓存不清程序）
- 用户文档目录

## 自定义清理

在 `cleanup.py` 的 `MACOS_CLEANUP_TARGETS` 或 `WINDOWS_CLEANUP_TARGETS` 中添加自定义目标：

```python
"my_custom": {
    "paths": ["~/my_custom_cache"],
    "desc": "我的自定义缓存",
    "safe": True,
}
```

命令型清理（如 Docker）：

```python
"docker": {
    "paths": [],
    "desc": "Docker 清理",
    "safe": True,
    "command": "docker system prune -f --volumes",
}
```
