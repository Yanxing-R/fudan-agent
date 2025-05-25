#!/bin/bash

# 激活 conda 环境
source /home/ecs-user/miniconda3/etc/profile.d/conda.sh
conda activate fudan-multi-agent

# 设置环境变量
export DASHSCOPE_API_KEY="sk-8563262fc3d74972bf6db1264427bef8"
export WECHAT_TOKEN="fudanAssistantToken2025"
export MONGODB_CONNECTION_STRING="mongodb+srv://doadmin:Dlb071iJ98Rz2m45@db-mongodb-sgp1-61006-64ec0530.mongo.ondigitalocean.com/yoda_probe_flask?tls=true&authSource=admin&replicaSet=db-mongodb-sgp1-61006"

# 进入项目目录
cd /home/ecs-user/fudan-agent

# 使用 gunicorn 启动应用（需要 sudo 权限绑定 80 端口）
sudo -E /home/ecs-user/miniconda3/envs/fudan-multi-agent/bin/gunicorn --bind 0.0.0.0:80 --workers 4 --timeout 300 --daemon --pid gunicorn.pid --access-logfile access.log --error-logfile error.log app:app

echo "应用已在后台启动，PID 文件: gunicorn.pid"
echo "访问日志: access.log"
echo "错误日志: error.log"
echo "要停止应用，请运行: kill \$(cat gunicorn.pid)" 