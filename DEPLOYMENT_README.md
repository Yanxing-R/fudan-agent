# 复旦智能体应用部署说明

## 环境信息
- **分支**: `dev/multi_agent_system`
- **Python 版本**: 3.13.2
- **虚拟环境**: `fudan-multi-agent` (miniconda)
- **运行端口**: 80 (需要 sudo 权限)

## 环境变量
```bash
DASHSCOPE_API_KEY=sk-8563262fc3d74972bf6db1264427bef8
WECHAT_TOKEN=fudanAssistantToken2025
MONGODB_CONNECTION_STRING=mongodb+srv://doadmin:Dlb071iJ98Rz2m45@db-mongodb-sgp1-61006-64ec0530.mongo.ondigitalocean.com/yoda_probe_flask?tls=true&authSource=admin&replicaSet=db-mongodb-sgp1-61006
```

## 管理脚本

### 启动应用
```bash
./start_app.sh
```
- 使用 gunicorn 后台运行
- 2 个 worker 进程
- 300 秒超时
- 生成 PID 文件 `gunicorn.pid`

### 停止应用
```bash
./stop_app.sh
```
- 优雅关闭所有进程
- 清理 PID 文件和残留进程

### 检查状态
```bash
./status_app.sh
```
- 检查进程状态
- 检查端口监听
- 测试应用响应
- 查看最新日志

### 重启应用
```bash
./restart_app.sh [选项]
```
选项:
- `--force`: 强制重启（即使应用未运行）
- `--logs`: 重启后显示日志
- `--help`: 显示帮助信息

### 查看日志
```bash
./logs_app.sh [类型] [行数]
```
类型:
- `error [lines]`: 查看错误日志（默认20行）
- `access [lines]`: 查看访问日志（默认20行）
- `both [lines]`: 查看两个日志文件（默认20行）
- `follow error`: 实时跟踪错误日志
- `follow access`: 实时跟踪访问日志
- `follow both`: 实时跟踪两个日志
- `clear`: 清空日志文件

## 日志文件
- **访问日志**: `access.log`
- **错误日志**: `error.log`

## API 接口

### 文本聊天接口
```bash
curl -X POST http://localhost/chat_text \
  -d "你好" \
  -H "Content-Type: text/plain"
```

### 微信回调接口
```
GET/POST /wechat
```

## 故障排除

1. **应用无法启动**
   - 检查 conda 环境是否激活
   - 检查环境变量是否正确设置
   - 查看 `error.log` 中的错误信息

2. **端口被占用**
   - 使用 `netstat -tlnp | grep 80` 检查端口使用情况
   - 修改 `start_app.sh` 中的端口配置
   - 注意：80 端口需要 sudo 权限

3. **MongoDB 连接问题**
   - 应用会自动降级，不影响基本功能
   - 检查网络连接和连接字符串

## 常用操作示例

### 快速重启并查看日志
```bash
./restart_app.sh --logs
```

### 查看最近的错误
```bash
./logs_app.sh error 50
```

### 实时监控访问日志
```bash
./logs_app.sh follow access
```

### 清空日志文件
```bash
./logs_app.sh clear
```

### 手动重启应用
```bash
./stop_app.sh && sleep 2 && ./start_app.sh
``` 