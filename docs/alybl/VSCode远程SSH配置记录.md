# VSCode Remote-SSH 配置记录

## 修改文件

`C:\Users\lmq\AppData\Roaming\Code - Insiders\User\settings.json`

## 新增配置项

```json
{
    "remote.SSH.useLocalServer": true,
    "remote.SSH.showLoginTerminal": true,
    "remote.SSH.enableRemoteCommand": true,
    "remote.SSH.useExecServer": false,
    "remote.SSH.remotePlatform": {
        "wxr-server": "windows"
    },
    "remote.autoForwardPorts": true,
    "remote.forwardOnOpen": true,
    "remote.localPortHost": "localhost",
    "remote.restoreForwardedPorts": true
}
```

## 配置说明

### SSH 连接核心配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `remote.SSH.useLocalServer` | `true` | 使用本地服务器模式，解决 Windows 远程连接兼容性 |
| `remote.SSH.showLoginTerminal` | `true` | 显示登录终端，方便查看认证过程 |
| `remote.SSH.enableRemoteCommand` | `true` | 允许远程命令执行 |
| `remote.SSH.useExecServer` | `false` | 禁用 exec server 模式，改用 local server 模式 |
| `remote.SSH.remotePlatform` | `{"wxr-server": "windows"}` | 指定远程平台为 Windows，避免 VSCode 误判为 Linux |

### 端口转发配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `remote.autoForwardPorts` | `true` | 自动检测并转发远程端口 |
| `remote.forwardOnOpen` | `true` | 自动转发终端/调试台打开的 URL |
| `remote.localPortHost` | `localhost` | 端口转发绑定到 localhost |
| `remote.restoreForwardedPorts` | `true` | 重连时恢复之前的端口转发 |

## SSH Config

文件路径：`C:\Users\lmq\.ssh\config`

```
Host wxr-server
    HostName 10.143.170.252
    User admin
    IdentityFile C:\Users\lmq\.ssh\id_ed25519_wxr
    ConnectTimeout 30
```

## 故障排除

### "拒绝访问"错误

远程 PowerShell 执行策略需设为 `RemoteSigned`：

```powershell
# 在远程服务器上执行
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
```

### VSCode Server 安装失败

1. `F1` → `Remote-SSH: Kill VS Code Server on Host` → 选择 `wxr-server`
2. `F1` → `Developer: Reload Window`
3. 重新连接

### 连接超时

SSH config 中 `ConnectTimeout 30` 已设置，如仍超时检查 ZeroTier 连接：

```powershell
ping 10.143.170.252
```