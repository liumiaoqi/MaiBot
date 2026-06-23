# 远程 WebUI 访问操作手册

## 环境信息

### 远程服务器（WXR 笔记本）

| 项目 | 值 |
|------|-----|
| ZeroTier IP | `10.143.170.252` |
| Radmin VPN IP | `26.105.89.182` |
| 公网 IP | `49.77.241.181` |
| 用户名 | `admin` |
| WebUI 端口 | `8001` |
| MaiBot 配置目录 | `C:\Users\admin\AppData\Roaming\MaiBotOneKeyDesktop\a9735f1edb36` |
| 登录 Token | `2a4f6ea176e6f3481a734486c9dfa945429647604dc13bfbdcf57025f805559e` |

### ZeroTier 网络

| 项目 | 值 |
|------|-----|
| Network ID | `76fc96e4985804e4` |
| 网络名称 | `LMQ_MC_CN` |

### SSH 密钥

| 项目 | 本地路径 |
|------|---------|
| 私钥 | `C:\Users\lmq\.ssh\id_ed25519_wxr` |
| 公钥 | `C:\Users\lmq\.ssh\id_ed25519_wxr.pub` |
| 注释 | `WXR` |

## 前置条件

### 本地电脑

1. **安装 ZeroTier**
   - 下载：https://www.zerotier.com/download/
   - 加入网络：`zerotier-cli join 76fc96e4985804e4`
   - 在 https://my.zerotier.com 授权设备

2. **验证连接**
   ```powershell
   ping 10.143.170.252
   ```

3. **SSH 密钥已生成**（如未生成）
   ```powershell
   ssh-keygen -t ed25519 -C "WXR" -f $env:USERPROFILE\.ssh\id_ed25519_wxr
   ```

### 远程服务器

1. **SSH 服务已启动**
   ```powershell
   Get-Service sshd  # 应显示 Running
   ```

2. **公钥已添加到 `administrators_authorized_keys`**
   ```powershell
   type "C:\ProgramData\ssh\administrators_authorized_keys"
   # 应显示：ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... WXR
   ```

3. **MaiBot WebUI 已启动**
   - 端口 8001 在监听
   - `host = "127.0.0.1"`（只允许本机访问，通过 SSH 隧道转发）

## 操作步骤

### 方法一：命令行 SSH 隧道（推荐）

```powershell
# 1. 建立 SSH 隧道（本地 4545 端口映射到远程 8001）
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr -L 4545:127.0.0.1:8001 -N admin@10.143.170.252

# 2. 保持窗口打开，不要关闭

# 3. 浏览器访问
# http://127.0.0.1:4545

# 4. 输入 Token 登录
# Token: 2a4f6ea176e6f3481a734486c9dfa945429647604dc13bfbdcf57025f805559e
```

**参数说明**：
- `-i`：指定私钥文件
- `-L 本地端口:远程目标:远程端口`：端口转发
- `-N`：不执行远程命令（只做端口转发）
- `-v`：显示详细日志（调试用）

### 方法二：后台运行 SSH 隧道

```powershell
# 后台启动
Start-Process ssh -ArgumentList "-i `"$env:USERPROFILE\.ssh\id_ed25519_wxr`" -N -L 4545:127.0.0.1:8001 admin@10.143.170.252" -WindowStyle Hidden

# 查看进程
Get-Process ssh

# 关闭隧道
Stop-Process -Name ssh
```

### 方法三：VSCode Remote-SSH

**配置 SSH config**：

```powershell
notepad C:\Users\lmq\.ssh\config
```

添加：

```
Host wxr-server
    HostName 10.143.170.252
    User admin
    IdentityFile C:\Users\lmq\.ssh\id_ed25519_wxr
    ConnectTimeout 30
```

**VSCode 连接**：

1. 安装扩展：`Remote - SSH`
2. `F1` → `Remote-SSH: Connect to Host` → 选择 `wxr-server`
3. 连接成功后，左侧可浏览远程文件

**VSCode 端口转发**：

1. 连接后，`F1` → `Simple Browser: Show`
2. 或在终端面板 → 端口 → 添加端口 `4545` → 转发到 `127.0.0.1:8001`

### 方法四：SSH config 配置端口转发

在 `C:\Users\lmq\.ssh\config` 中添加：

```
Host wxr-webui
    HostName 10.143.170.252
    User admin
    IdentityFile C:\Users\lmq\.ssh\id_ed25519_wxr
    LocalForward 4545 127.0.0.1:8001
    RequestTTY no
```

然后：

```powershell
ssh -N wxr-webui
# 浏览器访问 http://127.0.0.1:4545
```

## 故障排除

### 问题 1：ping 不通 ZeroTier IP

**原因**：本地未加入 ZeroTier 网络或未授权

**解决**：
```powershell
# 检查是否加入
zerotier-cli listnetworks

# 如未加入
zerotier-cli join 76fc96e4985804e4

# 在 https://my.zerotier.com 授权设备
```

### 问题 2：SSH 提示输入密码

**原因**：公钥未正确配置

**解决**（在远程服务器上）：
```powershell
# 检查 administrators_authorized_keys
type "C:\ProgramData\ssh\administrators_authorized_keys"

# 如不存在，创建
type C:\Users\admin\.ssh\authorized_keys | Out-File -FilePath "C:\ProgramData\ssh\administrators_authorized_keys" -Encoding ASCII

# 设置权限
icacls "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant "SYSTEM:F" /grant "Administrators:F"

# 重启 SSH
Restart-Service sshd
```

### 问题 3：连接成功但 WebUI 无法访问

**原因**：MaiBot 未运行或端口未监听

**解决**（在远程服务器上）：
```powershell
# 检查端口
netstat -an | findstr ":8001"

# 检查进程
Get-Process python -ErrorAction SilentlyContinue

# 启动 MaiBot（根据实际启动方式）
```

### 问题 4：VSCode 连接失败"拒绝访问"

**原因**：远程 PowerShell 执行策略限制

**解决**（在远程服务器上）：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## 快速命令参考

```powershell
# 测试 ZeroTier 连接
ping 10.143.170.252

# 建立 SSH 隧道
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr -L 4545:127.0.0.1:8001 -N admin@10.143.170.252

# 查看 SSH 隧道进程
Get-Process ssh

# 关闭所有 SSH 隧道
Stop-Process -Name ssh

# 远程执行命令
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr admin@10.143.170.252 "powershell -c \"命令\""

# 查看远程端口监听
ssh -i $env:USERPROFILE\.ssh\id_ed25519_wxr admin@10.143.170.252 "netstat -an | findstr :8001"
```

## 安全建议

1. **Token 保密**：不要分享登录 Token
2. **密钥保护**：私钥 `id_ed25519_wxr` 不要分享或上传
3. **VPN 优先**：通过 ZeroTier/Radmin VPN 访问，不开放公网端口
4. **定期更换**：定期更换 Token 和 SSH 密钥
5. **最小权限**：WebUI 保持 `host = "127.0.0.1"`，只通过 SSH 隧道访问