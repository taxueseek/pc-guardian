# 网络优化详细指南

## 诊断流程

1. **网络信息**：IP 地址、网关、Wi-Fi 信号
2. **Ping 测试**：Google DNS (8.8.8.8)、国内 DNS (114.114.114.114)、百度
3. **DNS 测试**：多域名解析延迟
4. **速度估算**：下载小文件估算连接速度

## 优化措施

### DNS 刷新
- macOS: `dscacheutil -flushcache` + `killall -HUP mDNSResponder`
- Windows: `ipconfig /flushdns`

### MTU 优化
- 默认 1500，PPPoE 环境建议 1492
- 脚本自动检测最佳 MTU

### Wi-Fi 优化建议
- 信号 > -50 dBm：优
- 信号 -50 ~ -65 dBm：良
- 信号 -65 ~ -75 dBm：中（建议靠近路由器）
- 信号 < -75 dBm：差（考虑换位置或加中继）

### DNS 推荐
- 国内：223.5.5.5（阿里）、114.114.114.114
- 国际：8.8.8.8（Google）、1.1.1.1（Cloudflare）
