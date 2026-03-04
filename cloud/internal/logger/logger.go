package logger

import (
	"log"
	"os"
)

var (
	Info  *log.Logger
	Error *log.Logger
)

// Init 初始化网关运维日志
func Init() error {
	// logs 目录
	if err := os.MkdirAll("logs", 0755); err != nil {
		return err
	}

	file, err := os.OpenFile(
		"logs/gateway.log",
		os.O_APPEND|os.O_CREATE|os.O_WRONLY,
		0644,
	)
	if err != nil {
		return err
	}

	flag := log.Ldate | log.Ltime | log.Lshortfile

	Info = log.New(file, "[INFO] ", flag)
	Error = log.New(file, "[ERROR] ", flag)

	// 防止直接用 log.Println 时丢日志
	log.SetOutput(file)

	return nil
}
