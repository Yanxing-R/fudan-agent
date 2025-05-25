#!/bin/bash

# 检查 PID 文件是否存在
if [ -f "gunicorn.pid" ]; then
    PID=$(cat gunicorn.pid)
    echo "正在停止应用 (PID: $PID)..."
    
    # 发送 TERM 信号进行优雅关闭
    kill -TERM $PID
    
    # 等待进程结束
    sleep 3
    
    # 检查进程是否还在运行
    if ps -p $PID > /dev/null; then
        echo "进程仍在运行，发送 KILL 信号强制终止..."
        kill -KILL $PID
        sleep 1
    fi
    
    # 再次检查
    if ps -p $PID > /dev/null; then
        echo "❌ 无法停止进程 $PID"
    else
        echo "✅ 应用已成功停止"
        rm -f gunicorn.pid
    fi
else
    echo "未找到 PID 文件 gunicorn.pid，应用可能未运行"
fi

# 清理可能残留的 gunicorn 进程
REMAINING=$(ps aux | grep gunicorn | grep -v grep | awk '{print $2}')
if [ ! -z "$REMAINING" ]; then
    echo "发现残留的 gunicorn 进程，正在清理..."
    echo $REMAINING | xargs kill -TERM
    sleep 2
    echo $REMAINING | xargs kill -KILL 2>/dev/null
fi

echo "应用停止操作完成" 