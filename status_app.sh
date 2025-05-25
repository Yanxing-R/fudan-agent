#!/bin/bash

echo "=== 复旦智能体应用状态检查 ==="
echo

# 检查 PID 文件
if [ -f "gunicorn.pid" ]; then
    PID=$(cat gunicorn.pid)
    echo "📄 PID 文件存在: $PID"
    
    # 检查进程是否实际运行
    if ps -p $PID > /dev/null; then
        echo "✅ 主进程正在运行 (PID: $PID)"
    else
        echo "❌ PID 文件存在但进程不在运行"
    fi
else
    echo "❌ 未找到 PID 文件"
fi

echo

# 检查所有 gunicorn 进程
PROCESSES=$(ps aux | grep gunicorn | grep -v grep)
if [ ! -z "$PROCESSES" ]; then
    echo "🚀 Gunicorn 进程:"
    echo "$PROCESSES"
else
    echo "❌ 未发现 Gunicorn 进程"
fi

echo

# 检查端口监听
if netstat -tlnp 2>/dev/null | grep -q ":80"; then
    echo "🔌 端口 80 正在监听:"
    netstat -tlnp 2>/dev/null | grep ":80"
else
    echo "❌ 端口 80 未监听"
fi

echo

# 检查应用响应
echo "🧪 测试应用响应..."
RESPONSE=$(curl -s -X POST http://localhost:80/chat_text -d "test" -H "Content-Type: text/plain" -w "%{http_code}")
HTTP_CODE="${RESPONSE: -3}"
BODY="${RESPONSE%???}"

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ 应用响应正常 (HTTP 200)"
    echo "📝 响应内容: ${BODY:0:100}..."
else
    echo "❌ 应用响应异常 (HTTP $HTTP_CODE)"
    echo "📝 响应内容: $BODY"
fi

echo

# 检查日志文件
if [ -f "error.log" ]; then
    echo "📋 错误日志最后 5 行:"
    tail -5 error.log
else
    echo "❌ 未找到错误日志文件"
fi

echo
echo "=== 状态检查完成 ===" 