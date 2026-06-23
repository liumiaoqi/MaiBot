# Linux 与 PowerShell 常用文件命令对照手册

## 目录导航

| 功能　　　　　 | Linux (Bash)      | PowerShell　　　　　　　　　　　　　　　　|                                        |
| ----------------| -------------------| -------------------------------------------| ----------------------------------------|
| 查看当前目录　 | `pwd`             | `Get-Location` (别名 `pwd`)　　　　　　　 |                                        |
| 切换目录　　　 | `cd /path/to/dir` | `Set-Location /path/to/dir` (别名 `cd`)　 |                                        |
| 列出文件　　　 | `ls -la`          | `Get-ChildItem -Force` (别名 `ls`, `dir`) |                                        |
| 列出指定扩展名 | `ls *.txt`        | `Get-ChildItem *.txt`　　　　　　　　　　 |                                        |
| 递归列出　　　 | `ls -R`           | `Get-ChildItem -Recurse`　　　　　　　　　|                                        |
| 按时间排序　　 | `ls -lt`          | `Get-ChildItem　　　　　　　　　　　　　　| Sort-Object LastWriteTime -Descending` |
| 按大小排序　　 | `ls -lS`          | `Get-ChildItem　　　　　　　　　　　　　　| Sort-Object Length -Descending`        |
| 树形显示　　　 | `tree`            | `tree` (CMD) 或 `Get-ChildItem -Recurse`　|                                        |

## 文件操作

| 功能 | Linux (Bash) | PowerShell |
|------|-------------|------------|
| 创建空文件 | `touch file.txt` | `New-Item file.txt -ItemType File` |
| 复制文件 | `cp src.txt dst.txt` | `Copy-Item src.txt dst.txt` (别名 `cp`) |
| 复制目录 | `cp -r src/ dst/` | `Copy-Item -Recurse src/ dst/` |
| 移动/重命名 | `mv old.txt new.txt` | `Move-Item old.txt new.txt` (别名 `mv`) |
| 删除文件 | `rm file.txt` | `Remove-Item file.txt` (别名 `rm`, `del`) |
| 删除目录 | `rm -r dir/` | `Remove-Item -Recurse -Force dir/` |
| 删除前确认 | `rm -i file.txt` | `Remove-Item file.txt -Confirm` |
| 创建目录 | `mkdir -p a/b/c` | `New-Item -ItemType Directory -Path a/b/c` (别名 `mkdir`) |
| 创建硬链接 | `ln src link` | `New-Item -ItemType HardLink -Path link -Target src` |
| 创建符号链接 | `ln -s src link` | `New-Item -ItemType SymbolicLink -Path link -Target src` |

## 文件查看

| 功能 | Linux (Bash) | PowerShell |
|------|-------------|------------|
| 查看全部内容 | `cat file.txt` | `Get-Content file.txt` (别名 `cat`) |
| 查看前 N 行 | `head -n 20 file.txt` | `Get-Content file.txt -TotalCount 20` (别名 `head`) |
| 查看后 N 行 | `tail -n 20 file.txt` | `Get-Content file.txt -Tail 20` (别名 `tail`) |
| 实时跟踪 | `tail -f file.txt` | `Get-Content file.txt -Wait -Tail 20` |
| 分页查看 | `less file.txt` | `more file.txt` 或 `Out-Host -Paging` |
| 查看文件类型 | `file file.txt` | `Get-Item file.txt | Select-Object Extension` |
| 查看文件信息 | `stat file.txt` | `Get-Item file.txt | Format-List *` |
| 查看文件大小 | `du -sh file.txt` | `(Get-Item file.txt).Length / 1MB` |
| 十六进制查看 | `hexdump -C file.bin` | `Format-Hex file.bin` |
| 比较文件 | `diff a.txt b.txt` | `Compare-Object (Get-Content a.txt) (Get-Content b.txt)` |

## 文件搜索

| 功能 | Linux (Bash) | PowerShell |
|------|-------------|------------|
| 按名称查找 | `find /path -name "*.txt"` | `Get-ChildItem -Path /path -Filter *.txt -Recurse` |
| 按内容搜索 | `grep -rn "pattern" /path` | `Select-String -Path /path/*.txt -Pattern "pattern" -Recurse` |
| 忽略大小写 | `grep -ri "pattern" /path` | `Select-String -Pattern "pattern" -SimpleMatch -CaseSensitive:$false` |
| 显示行号 | `grep -n "pattern" file` | `Select-String -Pattern "pattern" -Path file` (默认显示) |
| 只显示文件名 | `grep -rl "pattern" /path` | `Get-ChildItem -Recurse | Select-String -Pattern "pattern" | Select-Object -Unique Path` |
| 按大小查找 | `find /path -size +100M` | `Get-ChildItem -Recurse | Where-Object { $_.Length -gt 100MB }` |
| 按时间查找 | `find /path -mtime -7` | `Get-ChildItem -Recurse | Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-7) }` |
| 按权限查找 | `find /path -perm 755` | `Get-ChildItem -Recurse | Where-Object { $_.Mode -match "755" }` |
| 用 locate 快速查找 | `locate file.txt` | `Get-ChildItem -Recurse -Filter file.txt` (无等价物) |

## 文件权限与属性

| 功能 | Linux (Bash) | PowerShell |
|------|-------------|------------|
| 查看权限 | `ls -l file.txt` | `Get-Acl file.txt | Format-List` |
| 修改权限 | `chmod 755 file.txt` | `icacls file.txt /grant Everyone:F` |
| 递归修改权限 | `chmod -R 755 dir/` | `icacls dir/ /grant Everyone:F /T` |
| 修改所有者 | `chown user:group file` | `icacls file.txt /setowner "DOMAIN\User"` |
| 设置只读 | `chmod -w file.txt` | `Set-ItemProperty file.txt -Name IsReadOnly -Value $true` |
| 取消只读 | `chmod +w file.txt` | `Set-ItemProperty file.txt -Name IsReadOnly -Value $false` |

## 文件内容处理

| 功能　　 | Linux (Bash)                | PowerShell                                    |                         |                      |
| ----------| -----------------------------| -----------------------------------------------| -------------------------| ----------------------|
| 搜索替换 | `sed -i 's/old/new/g' file` | `(Get-Content file) -replace 'old','new' \    | Set-Content file`       |                      |
| 提取列　 | `awk '{print $2}' file`     | `Import-Csv file \                            | Select-Object Column2`  |                      |
| 排序去重 | `sort file \                | uniq`                                         | `Get-Content file \     | Sort-Object -Unique` |
| 统计行数 | `wc -l file.txt`            | `(Get-Content file.txt).Count`                |                         |                      |
| 统计字数 | `wc -w file.txt`            | `((Get-Content file.txt) -split '\s+').Count` |                         |                      |
| 截取列　 | `cut -d',' -f2 file.csv`    | `Import-Csv file.csv \                        | Select-Object Column2`  |                      |
| 合并文件 | `cat a.txt b.txt > c.txt`   | `Get-Content a.txt,b.txt \                    | Set-Content c.txt`      |                      |
| 反转行序 | `tac file.txt`              | `Get-Content file.txt \                       | Select-Object -Reverse` |                      |

## 压缩与解压

| 功能 | Linux (Bash) | PowerShell |
|------|-------------|------------|
| 压缩为 zip | `zip -r archive.zip dir/` | `Compress-Archive -Path dir/ -DestinationPath archive.zip` |
| 解压 zip | `unzip archive.zip` | `Expand-Archive -Path archive.zip -DestinationPath .` |
| 压缩为 tar.gz | `tar -czf archive.tar.gz dir/` | `tar -czf archive.tar.gz dir/` (需 tar 命令) |
| 解压 tar.gz | `tar -xzf archive.tar.gz` | `tar -xzf archive.tar.gz` |
| 压缩为 tar.bz2 | `tar -cjf archive.tar.bz2 dir/` | 无内置，用 7-Zip |
| 查看 zip 内容 | `unzip -l archive.zip` | `Add-Type -A System.IO.Compression; [IO.Compression.ZipFile]::OpenRead('archive.zip').Entries` |
| 查看 tar 内容 | `tar -tf archive.tar.gz` | `tar -tf archive.tar.gz` |

## 磁盘与空间

| 功能 | Linux (Bash) | PowerShell |
|------|-------------|------------|
| 磁盘使用情况 | `df -h` | `Get-PSDrive -PSProvider FileSystem \| Format-Table Name,Used,Free` |
| 目录大小 | `du -sh dir/` | `(Get-ChildItem -Recurse \| Measure-Object Length -Sum).Sum / 1MB` |
| 子目录大小 | `du -h --max-depth=1 dir/` | `Get-ChildItem -Directory \| ForEach-Object { $size = (Get-ChildItem $_.FullName -Recurse -File \| Measure-Object Length -Sum).Sum; [PSCustomObject]@{Name=$_.Name;SizeMB=[math]::Round($size/1MB,2)} }` |
| 文件系统类型 | `df -T` | `Get-Volume \| Format-Table DriveLetter,FileSystemLabel,FileSystem,SizeRemaining` |
| 挂载点 | `mount \| grep /dev/` | `Get-PSDrive -PSProvider FileSystem` |
| Inode 使用 | `df -i` | 无等价物 |

## 文件传输

| 功能 | Linux (Bash) | PowerShell |
|------|-------------|------------|
| SCP 上传 | `scp file user@host:/path` | `scp file user@host:/path` |
| SCP 下载 | `scp user@host:/path/file .` | `scp user@host:/path/file .` |
| SCP 目录 | `scp -r dir/ user@host:/path` | `scp -r dir/ user@host:/path` |
| SFTP | `sftp user@host` | `sftp user@host` |
| rsync 同步 | `rsync -avz src/ user@host:/dst/` | 无内置，用 cwRsync 或 rclone |
| 下载文件 | `wget URL` | `Invoke-WebRequest URL -OutFile file` (别名 `wget`) |
| 下载文件(curl) | `curl -O URL` | `Invoke-WebRequest URL -OutFile file` (别名 `curl`) |
| rclone 复制 | `rclone copy src remote:dst` | `rclone copy src remote:dst` |

## 管道与重定向

| 功能 | Linux (Bash) | PowerShell |
|------|-------------|------------|
| 输出重定向 | `cmd > file.txt` | `cmd \| Out-File file.txt` (别名 `>`) |
| 追加输出 | `cmd >> file.txt` | `cmd \| Out-File file.txt -Append` (别名 `>>`) |
| 错误重定向 | `cmd 2> err.txt` | `cmd 2> err.txt` |
| 合并输出 | `cmd &> all.txt` | `cmd *> all.txt` |
| 管道 | `cmd1 \| cmd2` | `cmd1 \| cmd2` |
| 输入重定向 | `cmd < file.txt` | `Get-Content file.txt \| cmd` |
| Here Document | `cat <<EOF > file` | `@"内容"@ \| Out-File file` |
| Tee | `cmd \| tee file.txt` | `cmd \| Tee-Object -FilePath file.txt` |

## 快捷技巧

### Linux

```bash
# 批量重命名
for f in *.txt; do mv "$f" "${f%.txt}.md"; done

# 查找并删除
find . -name "*.tmp" -delete

# 查找并执行
find . -name "*.log" -exec gzip {} \;

# 监控文件变化
inotifywait -m /path/to/dir

# 快速备份
cp file.txt{,.bak}
```

### PowerShell

```powershell
# 批量重命名
Get-ChildItem *.txt | Rename-Item -NewName { $_.Name -replace '\.txt$','.md' }

# 查找并删除
Get-ChildItem -Recurse -Filter *.tmp | Remove-Item

# 监控文件变化
Get-Content file.txt -Wait -Tail 20

# 快速备份
Copy-Item file.txt file.txt.bak

# 计算目录下各扩展名的文件数量
Get-ChildItem -Recurse -File | Group-Object Extension | Sort-Object Count -Descending | Format-Table Name, Count

# 查找大文件 Top 10
Get-ChildItem -Recurse -File | Sort-Object Length -Descending | Select-Object -First 10 FullName, @{N='SizeMB';E={[math]::Round($_.Length/1MB,2)}}

# 批量替换文件内容
Get-ChildItem -Recurse -Filter *.toml | ForEach-Object {
    (Get-Content $_.FullName) -replace 'old_value','new_value' | Set-Content $_.FullName
}
```