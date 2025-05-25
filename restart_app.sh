#!/bin/bash

echo "=== 复旦智能体应用重启 ==="
echo

# 检查是否有可选参数
FORCE_RESTART=false
SHOW_LOGS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_RESTART=true
            shift
            ;;
        --logs)
            SHOW_LOGS=true
            shift
            ;;
        --help|-h)
            echo "使用方法: $0 [选项]"
            echo "选项:"
            echo "  --force    强制重启（即使应用未运行）"
            echo "  --logs     重启后显示日志"
            echo "  --help     显示此帮助信息"
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            echo "使用 $0 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 检查应用当前状态
if [ -f "gunicorn.pid" ]; then
    PID=$(cat gunicorn.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "📍 检测到应用正在运行 (PID: $PID)"
        SHOULD_RESTART=true
    else
        echo "⚠️  PID 文件存在但进程不在运行"
        SHOULD_RESTART=true
    fi
else
    echo "❌ 应用似乎未运行（未找到 PID 文件）"
    if [ "$FORCE_RESTART" = true ]; then
        echo "🔄 使用 --force 选项，继续启动..."
        SHOULD_RESTART=true
    else
        echo "💡 如果要强制启动，请使用: $0 --force"
        SHOULD_RESTART=false
    fi
fi

if [ "$SHOULD_RESTART" = true ]; then
    echo
    echo "🛑 正在停止应用..."
    ./stop_app.sh
    
    echo
    echo "⏳ 等待 3 秒..."
    sleep 3
    
    echo
    echo "🚀 正在启动应用..."
    ./start_app.sh
    
    echo
    echo "⏳ 等待应用初始化..."
    sleep 5
    
    echo
    echo "🔍 检查应用状态..."
    ./status_app.sh
    
    # 检查启动是否成功
    if [ -f "gunicorn.pid" ]; then
        NEW_PID=$(cat gunicorn.pid)
        if ps -p $NEW_PID > /dev/null 2>&1; then
            echo
            echo "✅ 应用重启成功！新的 PID: $NEW_PID"
            
            # 如果指定了 --logs 选项，显示日志
            if [ "$SHOW_LOGS" = true ]; then
                echo
                echo "📋 显示最新日志:"
                echo "=================="
                ./logs_app.sh both 10
            fi
        else
            echo
            echo "❌ 应用启动失败！请检查错误日志:"
            ./logs_app.sh error 10
            exit 1
        fi
    else
        echo
        echo "❌ 重启失败，未找到新的 PID 文件"
        exit 1
    fi
else
    echo
    echo "❌ 重启操作已取消"
    exit 1
fi

echo
echo "🎉 重启操作完成！" 