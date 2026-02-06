#!/bin/bash
echo "正在使用 Docker 启动 Hyperliquid 跟单交易机器人..."
docker-compose up -d
echo ""
echo "机器人已启动！使用 'docker-compose logs -f' 查看日志"
echo "使用 'docker-compose down' 停止机器人"
