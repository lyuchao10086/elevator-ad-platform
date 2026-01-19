package main

import (
	"log"
	"net/http"

	"elevator_project/internal/gateway"
)

func main() {
	mgr := gateway.NewDeviceManager()
	handler := gateway.NewHandler(mgr)

	// --- 接口清单 ---
	// 1. 南向接口：给电梯连接用的
	http.HandleFunc("/ws", handler.HandleWebsocket)

	// 2. 北向接口：给 Python 调用的
	http.HandleFunc("/api/send", handler.HandleCommand)
	// 新增：仪表盘数据接口
	http.HandleFunc("/api/stats", handler.GetStats)

	// 新增：一个最简单的静态网页
	http.HandleFunc("/dashboard", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "dashboard.html")
	})
	log.Println("网关启动在 :8080")
	http.ListenAndServe(":8080", nil) //实现websocket/HTTP监听功能

}
