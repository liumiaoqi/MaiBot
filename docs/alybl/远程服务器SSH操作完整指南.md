# 远程服务器 SSH 操作完整指南

## 环境信息

### 远程服务器（WXR 笔记本）

| 项目 | 值 |
|------|-----|
| ZeroTier IP | `10.143.170.252` |
| Radmin VPN IP | `26.105.89.182` |
| 公网 IP | `49.77.241.181` |
| 用户名 | `admin` |
| MaiBot 配置目录 | `C:\Users\admin\AppData\Roaming\MaiBotOneKeyDesktop\a9735f1edb36` |
| WebUI 端口 | `8001` |
| WebUI Token | `2a4f6ea176e6f3481a734486c9dfa945429647604dc13bfbdcf57025f805559e` |

### ZeroTier 网络

| 项目 | 值 |
|------|-----|
| Network ID | `76fc96e4985804e4` |
| 网络名称 | `LMQ_MC_CN` |

### SSH 密钥

| 项目 | 路径 |
|------|------|
| 私钥 | `C:\Users\lmq\.ssh\id_ed25519_wxr` |
| 公钥 | `C:\Users\lmq\.ssh\id_ed25519_wxr.pub` |

### SSH Config

文件：`C:\Users\lmq\.ssh\config`

```
Host wxr-server
    HostName 10.143.170.252
    User admin
    IdentityFile C:\Users\lmq\.ssh\id_ed25519_wxr
    ConnectTimeout 30
```

---

## 一、基础连接

### 1.1 交互式登录

```powershell
# 使用 SSH config 别名
ssh wxr-server

# 或完整命令
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr admin@10.143.170.252
```

登录后进入远程 CMD，输入 `powershell` 切换到 PowerShell。

### 1.2 远程执行单条命令

```powershell
# 执行 CMD 命令
ssh wxr-server "dir C:\Users\admin"

# 执行 PowerShell 命令
ssh wxr-server "powershell -c \"Get-Process python -ErrorAction SilentlyContinue\""

# 查看端口监听
ssh wxr-server "netstat -an | findstr :8001"

# 查看文件内容
ssh wxr-server "powershell -c \"Get-Content 'C:\Users\admin\AppData\Roaming\MaiBotOneKeyDesktop\a9735f1edb36\config\bot_config.toml' | Select-String 'webui'\""
```

### 1.3 调试连接

```powershell
# 详细日志
ssh -v wxr-server

# 更详细日志
ssh -vv wxr-server

# 最详细日志
ssh -vvv wxr-server
```

---

## 二、端口转发（访问远程 WebUI）

### 2.1 本地端口转发

```powershell
# 本地 4545 端口映射到远程 127.0.0.1:8001
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr -L 4545:127.0.0.1:8001 -N admin@10.143.170.252

# 浏览器访问
# http://127.0.0.1:4545
```

**参数说明**：
- `-L 本地端口:远程目标IP:远程端口`：本地端口转发
- `-N`：不执行远程命令（只做转发）
- `-f`：后台运行

### 2.2 多端口转发

```powershell
# 同时转发 WebUI(8001) + 插件WebUI(8121)
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr `
    -L 4545:127.0.0.1:8001 `
    -L 4546:127.0.0.1:8121 `
    -N admin@10.143.170.252

# 访问：
# http://127.0.0.1:4545  → MaiBot WebUI
# http://127.0.0.1:4546  → 插件 WebUI
```

### 2.3 后台运行隧道

```powershell
# 启动后台隧道
Start-Process ssh -ArgumentList "-i `"$env:USERPROFILE\.ssh\id_ed25519_wxr`" -N -L 4545:127.0.0.1:8001 admin@10.143.170.252" -WindowStyle Hidden

# 查看隧道进程
Get-Process ssh | Where-Object { $_.CommandLine -like "*4545*" }

# 关闭所有 SSH 隧道
Stop-Process -Name ssh

# 关闭特定进程
Stop-Process -Id <PID>
```

### 2.4 SSH Config 配置端口转发

在 `C:\Users\lmq\.ssh\config` 中添加：

```
Host wxr-webui
    HostName 10.143.170.252
    User admin
    IdentityFile C:\Users\lmq\.ssh\id_ed25519_wxr
    LocalForward 4545 127.0.0.1:8001
    LocalForward 4546 127.0.0.1:8121
    RequestTTY no
```

使用：

```powershell
ssh -N wxr-webui
```

---

## 三、文件传输

### 3.1 SCP 传文件

```powershell
# 本地 → 远程：上传文件
scp -i $env:USERPROFILE\.ssh\id_ed25519_wxr "本地文件路径" admin@10.143.170.252:"远程目标路径"

# 示例：上传配置文件
scp -i $env:USERPROFILE\.ssh\id_ed25519_wxr "E:\config\bot_config.toml" admin@10.143.170.252:"C:\Users\admin\AppData\Roaming\MaiBotOneKeyDesktop\a9735f1edb36\config\bot_config.toml"

# 远程 → 本地：下载文件
scp -i $env:USERPROFILE\.ssh\id_ed25519_wxr admin@10.143.170.252:"远程文件路径" "本地目标路径"

# 示例：下载日志
scp -i $env:USERPROFILE\.ssh\id_ed25519_wxr admin@10.143.170.252:"C:\Users\admin\AppData\Roaming\MaiBotOneKeyDesktop\a9735f1edb36\logs\app_20260623.log.jsonl" "E:\logs\"

# 上传整个目录（-r 递归）
scp -i $env:USERPROFILE\.ssh\id_ed25519_wxr -r "E:\plugins\qq_user_memory_plugin" admin@10.143.170.252:"C:\Users\admin\AppData\Roaming\MaiBotOneKeyDesktop\a9735f1edb36\plugins\"

# 下载整个目录
scp -i $env:USERPROFILE\.ssh\id_ed25519_wxr -r admin@10.143.170.252:"C:\Users\admin\AppData\Roaming\MaiBotOneKeyDesktop\a9735f1edb36\logs" "E:\remote_logs\"
```

### 3.2 使用 SSH Config 别名简化

```powershell
# 配置别名后，scp 更简洁
scp "E:\config\bot_config.toml" wxr-server:"C:\Users\admin\config\"

scp wxr-server:"C:\Users\admin\logs\app.log" "E:\logs\"

scp -r "E:\plugins\my_plugin" wxr-server:"C:\Users\admin\plugins\"
```

### 3.3 SFTP 交互式传输

```powershell
# 启动 SFTP 会话
sftp -i $env:USERPROFILE\.ssh\id_ed25519_wxr admin@10.143.170.252

# 或用别名
sftp wxr-server
```

SFTP 内部命令：

```
# 上传文件
put "E:\local\file.txt" "C:\Users\admin\remote\file.txt"

# 下载文件
get "C:\Users\admin\remote\file.txt" "E:\local\file.txt"

# 上传目录（递归）
put -r "E:\local\dir" "C:\Users\admin\remote\dir"

# 下载目录（递归）
get -r "C:\Users\admin\remote\dir" "E:\local\dir"

# 查看远程目录
ls "C:\Users\admin\"

# 查看本地目录
lls "E:\"

# 切换远程目录
cd "C:\Users\admin\logs"

# 切换本地目录
lcd "E:\logs"

# 退出
exit
```

### 3.4 通过 SSH 管道传输

```powershell
# 远程文件内容直接输出到本地
ssh wxr-server "powershell -c \"Get-Content 'C:\Users\admin\config\bot_config.toml'\"" > E:\local_copy.toml

# 本地文件内容写入远程
Get-Content "E:\config\bot_config.toml" | ssh wxr-server "powershell -c \"Set-Content -Path 'C:\Users\admin\config\bot_config.toml' -Value (Get-Content)\""
```

---

## 四、远程管理

### 4.1 进程管理

```powershell
# 查看 Python 进程
ssh wxr-server "powershell -c \"Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime\""

# 查看 MaiBot 相关进程
ssh wxr-server "powershell -c \"Get-Process | Where-Object { `$_.MainWindowTitle -like '*MaiBot*' -or `$_.ProcessName -like '*python*' } | Select-Object Id, ProcessName\""

# 终止进程
ssh wxr-server "powershell -c \"Stop-Process -Id <PID> -Force\""
```

### 4.2 服务管理

```powershell
# 查看 SSH 服务状态
ssh wxr-server "powershell -c \"Get-Service sshd | Select-Object Status, Name\""

# 重启 SSH 服务
ssh wxr-server "powershell -c \"Restart-Service sshd\""
```

### 4.3 系统信息

```powershell
# 磁盘空间
ssh wxr-server "powershell -c \"Get-PSDrive C | Select-Object Used, Free\""

# 内存使用
ssh wxr-server "powershell -c \"Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory, TotalVisibleMemorySize\""

# 系统运行时间
ssh wxr-server "powershell -c \"(Get-CimInstance Win32_OperatingSystem).LastBootUpTime\""

# 网络连接
ssh wxr-server "netstat -an | findstr :8001"
```

### 4.4 防火墙管理

```powershell
# 查看规则
ssh wxr-server "netsh advfirewall firewall show rule name=SSH"

# 添加规则
ssh wxr-server "netsh advfirewall firewall add rule name=SSH dir=in action=allow protocol=tcp localport=22"
```

---

## 五、VSCode Remote-SSH

### 5.1 配置

**SSH Config**（`C:\Users\lmq\.ssh\config`）：

```
Host wxr-server
    HostName 10.143.170.252
    User admin
    IdentityFile C:\Users\lmq\.ssh\id_ed25519_wxr
    ConnectTimeout 30
```

**VSCode Settings**（`C:\Users\lmq\AppData\Roaming\Code - Insiders\User\settings.json`）：

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

### 5.2 连接步骤

1. 安装扩展：`Remote - SSH`
2. `F1` → `Remote-SSH: Connect to Host` → 选择 `wxr-server`
3. 连接成功后：
   - 左侧资源管理器可浏览远程文件
   - 终端自动打开远程 PowerShell
   - 可编辑远程文件并保存

### 5.3 端口转发

连接后在 VSCode 底部"PORTS"面板：

1. 点击"Forward a Port"
2. 输入 `8001`
3. 自动映射到本地，点击链接即可访问

### 5.4 文件操作

- **浏览**：左侧资源管理器 → 打开远程文件夹
- **编辑**：直接打开远程文件编辑，保存即时生效
- **上传/下载**：右键文件 → "Download" / 拖拽本地文件到远程目录

---

## 六、常用操作速查

### 快速访问 WebUI

```powershell
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr -L 4545:127.0.0.1:8001 -N admin@10.143.170.252
# 浏览器 → http://127.0.0.1:4545
# Token → 2a4f6ea176e6f3481a734486c9dfa945429647604dc13bfbdcf57025f805559e
```

### 快速上传文件

```powershell
scp -i $env:USERPROFILE\.ssh\id_ed25519_wxr "本地文件" wxr-server:"远程路径"
```

### 快速下载文件

```powershell
scp -i $env:USERPROFILE\.ssh\id_ed25519_wxr wxr-server:"远程文件" "本地路径"
```

### 快速查看远程状态

```powershell
ssh wxr-server "netstat -an | findstr :8001"
```

### 远程执行 PowerShell

```powershell
ssh wxr-server "powershell -c \"命令\""
```

---

## 七、故障排除

### SSH 连接超时

```powershell
# 检查 ZeroTier 连接
ping 10.143.170.252

# 如不通，检查 ZeroTier 服务
zerotier-cli listnetworks

# 重新加入网络
zerotier-cli join 76fc96e4985804e4
```

### 密钥认证失败

```powershell
# 在远程服务器上检查
ssh wxr-server "powershell -c \"type C:\ProgramData\ssh\administrators_authorized_keys\""

# 如文件不存在，在远程服务器上创建
ssh wxr-server
# 进入远程后执行：
powershell
type C:\Users\admin\.ssh\authorized_keys | Out-File -FilePath "C:\ProgramData\ssh\administrators_authorized_keys" -Encoding ASCII
icacls "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant "SYSTEM:F" /grant "Administrators:F"
Restart-Service sshd
```

### SCP 中文路径乱码

```powershell
# 使用短路径格式
ssh wxr-server "powershell -c \"(New-Object -ComObject Scripting.FileSystemObject).GetFolder('C:\Users\admin\AppData\Roaming\MaiBotOneKeyDesktop\a9735f1edb36').ShortPath\""

# 用返回的短路径（如 C:\Users\admin\APPLIC~1\MaiBo~1\a9735~1）替代
scp wxr-server:"C:\Users\admin\APPLIC~1\MaiBo~1\a9735~1\config\bot_config.toml" "E:\"
```

### VSCode Remote-SSH "拒绝访问"

```powershell
# 在远程服务器上设置执行策略
ssh wxr-server "powershell -c \"Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force\""
```

### 端口转发不生效

```powershell
# 检查本地端口是否被占用
netstat -an | findstr :4545

# 换一个本地端口
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr -L 5555:127.0.0.1:8001 -N admin@10.143.170.252
```