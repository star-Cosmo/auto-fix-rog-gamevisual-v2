# 安全政策

## 支持的版本

| 版本 | 支持情况 |
|---|---|
| 2.x | ✅ 支持 |

## 本工具的安全边界

- 本工具**纯本地运行**，不联网上传任何数据（唯一的网络行为是 Bootstrap 缺 Python 时从官方源/镜像下载便携版 Python）
- 写入范围仅限：`C:\ProgramData\ASUS\GameVisual\`、`C:\Windows\System32\spool\drivers\color\`，以及本仓库目录内的 `_python\` 运行时
- 每次修改前自动备份到 `C:\ProgramData\ASUS\GameVisual_backup_时间戳\`
- 不写注册表、不安装服务、不添加自启

## 报告漏洞

发现安全漏洞（如：路径注入、提权滥用、下载源被劫持的防护缺陷等）请**不要开公开 Issue**，直接邮件联系：

**chenbin2004sz@163.com**

收到后 72 小时内回复，确认后尽快修复并发版，修复后在 Release 说明中致谢（除非你希望匿名）。
