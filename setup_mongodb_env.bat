@echo off
echo ============================================
echo 复旦校园助手 MongoDB 环境变量配置脚本
echo ============================================
echo.

echo 此脚本将帮助您配置 MongoDB 连接环境变量
echo 如果您不需要 MongoDB 同步功能，可以跳过此步骤
echo.

set MONGODB_URI=mongodb+srv://doadmin:Dlb071iJ98Rz2m45@db-mongodb-sgp1-61006-64ec0530.mongo.ondigitalocean.com/fudan_agent?tls=true^&authSource=admin^&replicaSet=db-mongodb-sgp1-61006

echo 正在设置环境变量...
setx MONGODB_CONNECTION_STRING "%MONGODB_URI%"

if %errorlevel% equ 0 (
    echo.
    echo ✅ MongoDB 连接字符串已成功设置！
    echo.
    echo 环境变量名: MONGODB_CONNECTION_STRING
    echo 连接字符串: %MONGODB_URI%
    echo.
    echo 💡 注意：
    echo 1. 环境变量将在新的命令行窗口中生效
    echo 2. 如果不需要 MongoDB 功能，系统会自动回退到本地文件模式
    echo 3. 您也可以手动设置此环境变量：
    echo    - 系统属性 ^> 高级 ^> 环境变量
    echo    - 或在 PowerShell 中运行：$env:MONGODB_CONNECTION_STRING = "连接字符串"
    echo.
) else (
    echo.
    echo ❌ 设置环境变量失败，请尝试：
    echo 1. 以管理员身份运行此脚本
    echo 2. 或手动设置环境变量
    echo.
)

echo 按任意键退出...
pause >nul 