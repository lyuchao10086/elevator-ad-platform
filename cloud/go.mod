module github.com/lyuchao10086/elevator-ad-platform/cloud

go 1.25.5

require github.com/gorilla/websocket v1.5.3

require github.com/lyuchao10086/elevator-ad-platform/shared v0.0.0

require (
	github.com/aliyun/aliyun-oss-go-sdk v3.0.2+incompatible // indirect
	golang.org/x/time v0.14.0 // indirect
)

replace github.com/lyuchao10086/elevator-ad-platform/shared => ../shared
