#!/bin/bash

# 日志查看脚本
echo "=== 复旦智能体应用日志查看 ==="
echo

# 检查参数
if [ $# -eq 0 ]; then
    echo "使用方法:"
    echo "  $0 error [lines]     - 查看错误日志（默认最后20行）"
    echo "  $0 access [lines]    - 查看访问日志（默认最后20行）"
    echo "  $0 both [lines]      - 查看两个日志文件（默认最后20行）"
    echo "  $0 follow error      - 实时跟踪错误日志"
    echo "  $0 follow access     - 实时跟踪访问日志"
    echo "  $0 follow both       - 实时跟踪两个日志"
    echo "  $0 clear             - 清空日志文件"
    echo
    echo "示例:"
    echo "  $0 error 50          - 查看错误日志最后50行"
    echo "  $0 follow error      - 实时跟踪错误日志"
    exit 1
fi

LOG_TYPE="$1"
LINES="${2:-20}"

case "$LOG_TYPE" in
    "error")
        if [ -f "error.log" ]; then
            echo "📋 错误日志最后 $LINES 行:"
            echo "=================="
            tail -n "$LINES" error.log
        else
            echo "❌ 错误日志文件不存在"
        fi
        ;;
        
    "access")
        if [ -f "access.log" ]; then
            echo "📊 访问日志最后 $LINES 行:"
            echo "=================="
            tail -n "$LINES" access.log
        else
            echo "❌ 访问日志文件不存在"
        fi
        ;;
        
    "both")
        echo "📋 错误日志最后 $LINES 行:"
        echo "=================="
        if [ -f "error.log" ]; then
            tail -n "$LINES" error.log
        else
            echo "❌ 错误日志文件不存在"
        fi
        
        echo
        echo "📊 访问日志最后 $LINES 行:"
        echo "=================="
        if [ -f "access.log" ]; then
            tail -n "$LINES" access.log
        else
            echo "❌ 访问日志文件不存在"
        fi
        ;;
        
    "follow")
        FOLLOW_TYPE="$2"
        case "$FOLLOW_TYPE" in
            "error")
                if [ -f "error.log" ]; then
                    echo "🔄 实时跟踪错误日志 (Ctrl+C 退出):"
                    echo "================================"
                    tail -f error.log
                else
                    echo "❌ 错误日志文件不存在"
                fi
                ;;
            "access")
                if [ -f "access.log" ]; then
                    echo "🔄 实时跟踪访问日志 (Ctrl+C 退出):"
                    echo "================================"
                    tail -f access.log
                else
                    echo "❌ 访问日志文件不存在"
                fi
                ;;
            "both")
                echo "🔄 实时跟踪所有日志 (Ctrl+C 退出):"
                echo "================================"
                if [ -f "error.log" ] && [ -f "access.log" ]; then
                    tail -f error.log access.log
                elif [ -f "error.log" ]; then
                    echo "只有错误日志可用:"
                    tail -f error.log
                elif [ -f "access.log" ]; then
                    echo "只有访问日志可用:"
                    tail -f access.log
                else
                    echo "❌ 没有可用的日志文件"
                fi
                ;;
            *)
                echo "❌ 无效的跟踪类型，请使用: error, access, 或 both"
                ;;
        esac
        ;;
        
    "clear")
        echo "⚠️  准备清空日志文件..."
        read -p "确认清空所有日志? (y/N): " confirm
        if [[ $confirm =~ ^[Yy]$ ]]; then
            > error.log 2>/dev/null || echo "⚠️ 无法清空 error.log"
            > access.log 2>/dev/null || echo "⚠️ 无法清空 access.log"
            echo "✅ 日志文件已清空"
        else
            echo "❌ 操作已取消"
        fi
        ;;
        
    *)
        echo "❌ 无效的日志类型，请使用: error, access, both, follow, 或 clear"
        exit 1
        ;;
esac 