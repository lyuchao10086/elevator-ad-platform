module elevator_project

go 1.25.5

require github.com/gorilla/websocket v1.5.3

require github.com/lyuchao10086/elevator-ad-platform/shared v0.0.0

require (
	github.com/aliyun/aliyun-oss-go-sdk v3.0.2+incompatible // indirect
	golang.org/x/time v0.14.0 // indirect
)

replace github.com/lyuchao10086/elevator-ad-platform/shared => ../shared
require (
	github.com/cespare/xxhash/v2 v2.3.0 // indirect
	github.com/dgryski/go-rendezvous v0.0.0-20200823014737-9f7001d12a5f // indirect
	github.com/gorilla/websocket v1.5.3 // indirect
	github.com/redis/go-redis/v9 v9.17.2 // indirect
)
