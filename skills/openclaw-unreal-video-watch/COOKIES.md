# Chrome Cookies 说明

当 YouTube 提示 `Sign in to confirm you're not a bot` 时，这个 Skill 需要读取你自己的登录态。

## 优先级

这个 Skill 会按下面顺序尝试认证：

1. `%LOCALAPPDATA%\OpenClawUnrealVideoWatch\cookies.txt`
2. `secrets/cookies.txt`
3. `config/watch_config.json` 里的 `cookies_from_browser`
4. 匿名访问

最推荐把 cookies 放在第 1 个位置。这样重装 Skill 目录时不会被覆盖。

## 方案 A：直接使用 Chrome 登录态

前提：

- 你已经在 Chrome 里登录了 YouTube
- `config/watch_config.json` 里包含：

```json
"cookies_from_browser": ["chrome", "edge"]
```

运行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\run.ps1"
```

如果仍然失败，通常是本机浏览器 Cookie 数据库无法被当前环境稳定读取。这时改用方案 B。

## 方案 B：导出 cookies.txt

推荐目标文件：

`%LOCALAPPDATA%\OpenClawUnrealVideoWatch\cookies.txt`

兼容目标文件：

`.\secrets\cookies.txt`

要求格式：

- Netscape cookies format
- 文件名固定为 `cookies.txt`

常见做法：

1. 在 Chrome 中确认你已经登录 YouTube。
2. 使用支持导出 Netscape cookies 的浏览器扩展，把 `youtube.com` 的 cookies 导出为文本文件。
3. 将导出的文件保存为：

```text
C:\Users\你的用户名\AppData\Local\OpenClawUnrealVideoWatch\cookies.txt
```

4. 再次运行：

```powershell
powershell -ExecutionPolicy Bypass -File ".\run.ps1"
```

## 放置后的效果

- 脚本会优先读取 `%LOCALAPPDATA%\OpenClawUnrealVideoWatch\cookies.txt`
- 不再依赖浏览器数据库是否可访问
- 更适合计划任务和无人值守运行
- 重新安装或覆盖 Skill 目录时，不会丢失 cookies

## 安全提醒

- `cookies.txt` 等同于你的登录态，请不要发给别人
- 这个文件不要提交到 Git，不要同步到公共仓库
- 如果怀疑泄露，请尽快退出相关设备登录或刷新账号会话

## 推荐做法

如果是你自己电脑上手动运行：

- 先试 Chrome 浏览器登录态

如果是定时任务或长期运行：

- 更推荐 `%LOCALAPPDATA%\OpenClawUnrealVideoWatch\cookies.txt`

## SSL 证书说明

如果目标机器上的嵌入式运行环境缺少完整证书链，`yt-dlp` 可能报：

`CERTIFICATE_VERIFY_FAILED`

这个 Skill 默认已经在 `config/watch_config.json` 里启用了：

```json
"no_check_certificates": true
```

这样会给 `yt-dlp` 自动附加 `--no-check-certificates`，避免 Windows 嵌入式环境下的证书链问题。
