package main

import (
	"log"
	"net/http"

	"elevator_project/internal/gateway"

	"github.com/joho/godotenv"
)

func main() {
	//加载环境配置
	err := godotenv.Load(".env")

	// 如果上面的失败了，尝试往上一级找 (针对在 cmd 目录下运行的情况)
	if err != nil {
		err = godotenv.Load("../.env")
	}

	if err != nil {
		log.Println("未加载到 .env 文件，将使用系统环境变量")
	} else {
		log.Println("成功加载 .env 配置")
	}

	mgr := gateway.NewDeviceManager()

	// ✅ 在程序启动时初始化 OSS
	bucket := gateway.InitOSSBucket()

	handler := gateway.NewHandler(mgr, bucket)

	// --- 接口清单 ---
	// 1. 南向接口：给电梯连接用的
	http.HandleFunc("/ws", handler.HandleWebsocket)

	// 2. 北向接口：给 Python 调用的
	http.HandleFunc("/api/send", handler.HandleCommand)
	// 新增：python触发设备截图
	http.HandleFunc("/api/v1/devices/remote/", handler.HandleRemoteSnapshot)
	// 新增：仪表盘数据接口
	http.HandleFunc("/api/stats", handler.GetStats)

	// 新增：一个最简单的静态网页
	http.HandleFunc("/dashboard", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFile(w, r, "dashboard.html")
	})
	log.Println("网关启动在 :8080")
	http.ListenAndServe(":8080", nil) //实现websocket/HTTP监听功能

}
