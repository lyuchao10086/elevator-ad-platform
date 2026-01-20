package main

import (
	"log"
	"net/http"

	"github.com/lyuchao10086/elevator-ad-platform/cloud/internal/gateway"
)

func main() {
	mgr := gateway.NewDeviceManager()

	// ✅ 在程序启动时初始化 OSS
	bucket := gateway.InitOSSBucket()

	handler := gateway.NewHandler(mgr, bucket)

	// --- 接口清单 ---
	// 1. 南向接口：给电梯连接用的
	http.HandleFunc("/ws", handler.HandleWebsocket)

	// 2. 北向接口：给 Python 调用的
	http.HandleFunc("/api/send", handler.HandleCommand)

	log.Println("网关启动在 :8080")
	http.ListenAndServe(":8080", nil) //实现websocket/HTTP监听功能
}
