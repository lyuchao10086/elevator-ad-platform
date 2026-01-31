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
		log.Printf("[OSS] 环境变量未配置完整，OSS 上传将被禁用")
		return nil
	}

	client, err := oss.New(endpoint, accessKey, secretKey)
	if err != nil {
		log.Printf("[OSS] 创建 client 失败，OSS 上传将被禁用: %v", err)
		return nil
	}

	bucket, err := client.Bucket(bucketName)
	if err != nil {
		log.Printf("[OSS] 获取 bucket 失败，OSS 上传将被禁用: %v", err)
		return nil
	}

	log.Printf("[OSS] Bucket 初始化成功: %s", bucketName)
	return bucket
}
