package gateway

import (
	"log"
	"os"

	"github.com/aliyun/aliyun-oss-go-sdk/oss"
)

func InitOSSBucket() *oss.Bucket {
	endpoint := os.Getenv("OSS_ENDPOINT")
	accessKey := os.Getenv("OSS_ACCESS_KEY")
	secretKey := os.Getenv("OSS_SECRET_KEY")
	bucketName := os.Getenv("OSS_BUCKET")

	if endpoint == "" || accessKey == "" || secretKey == "" || bucketName == "" {
		log.Println("[OSS] 警告：未检测到云存储配置，截图功能将暂时失效，但不影响其他功能运行。")
		return nil
	}

	client, err := oss.New(endpoint, accessKey, secretKey)
	if err != nil {
		log.Fatalf("[OSS] 创建 client 失败: %v", err)
	}

	bucket, err := client.Bucket(bucketName)
	if err != nil {
		log.Fatalf("[OSS] 获取 bucket 失败: %v", err)
	}

	log.Printf("[OSS] Bucket 初始化成功: %s", bucketName)
	return bucket
}
