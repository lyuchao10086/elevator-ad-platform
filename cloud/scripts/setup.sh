#!/bin/bash
# cloud/scripts/setup.sh

echo "=== 设置Go网关项目 ==="

# 1. 初始化Go模块
cd ../cloud
go mod init ggithub.com/lyuchao10086/elevator-ad-platform/cloud

# 2. 安装依赖
echo "安装依赖..."
go get github.com/gorilla/websocket
go get google.golang.org/grpc
go get github.com/spf13/viper
go get go.uber.org/zap
go get github.com/prometheus/client_golang

# 3. 生成代码（如果需要）
echo "生成gRPC代码..."
protoc --go_out=. --go-grpc_out=. \
    -I../../shared/proto \
    ../../shared/proto/*.proto

# 4. 创建示例配置
cp configs/config.yaml.example configs/config.yaml

echo "✅ 项目设置完成！"
echo "运行: go run cmd/gateway/main.go"