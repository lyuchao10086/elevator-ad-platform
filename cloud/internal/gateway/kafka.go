package gateway

import (
	"log"
	"os"
	"strings"

	"github.com/IBM/sarama"
)

type KafkaProducer struct {
	producer sarama.SyncProducer
	topic    string
}

func InitKafkaProducer() *KafkaProducer {
	brokersEnv := os.Getenv("KAFKA_BROKERS")
	topic := os.Getenv("KAFKA_PLAYLOG_TOPIC")

	if brokersEnv == "" || topic == "" {
		log.Println("[kafka] 未配置，Kafka 功能关闭")
		return nil
	}

	brokers := strings.Split(brokersEnv, ",")

	producer, err := NewKafkaProducer(brokers, topic)
	if err != nil {
		log.Fatalf("[kafka] 初始化失败: %v", err)
	}

	log.Println("[kafka] Producer 初始化成功")
	return producer
}

// 初始化
func NewKafkaProducer(brokers []string, topic string) (*KafkaProducer, error) {
	cfg := sarama.NewConfig()
	cfg.Producer.RequiredAcks = sarama.WaitForAll
	cfg.Producer.Retry.Max = 5
	cfg.Producer.Return.Successes = true
	cfg.Version = sarama.V3_6_0_0

	p, err := sarama.NewSyncProducer(brokers, cfg)
	if err != nil {
		return nil, err
	}

	log.Printf("[kafka] producer ready, topic=%s", topic)

	return &KafkaProducer{
		producer: p,
		topic:    topic,
	}, nil
}

// 发送消息
func (k *KafkaProducer) Send(key string, value []byte) error {
	msg := &sarama.ProducerMessage{
		Topic: k.topic,
		Key:   sarama.StringEncoder(key),
		Value: sarama.ByteEncoder(value),
	}
	_, _, err := k.producer.SendMessage(msg)
	if err != nil {
		log.Printf("[kafka] send failed: %v", err)
	}
	return err
}

// 关闭
func (k *KafkaProducer) Close() {
	if err := k.producer.Close(); err != nil {
		log.Printf("[kafka] close error: %v", err)
	}
}
