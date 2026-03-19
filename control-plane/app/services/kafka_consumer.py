"""
Kafka consumer service for consuming play logs from gateway and persisting to PostgreSQL.

This service:
1. Subscribes to the 'play_logs' topic from Kafka
2. Deserializes JSON messages containing playback logs from edge devices
3. Deduplicates logs by log_id (using PostgreSQL UPSERT)
4. Stores logs to the ad_logs table
5. Handles data type conversions and timestamp normalization
"""

import json
import logging
import os
import time
from typing import Dict, Optional
from datetime import datetime
from app.services.db_service import get_conn

logger = logging.getLogger(__name__)


class KafkaPlayLogConsumer:
    """Kafka consumer for play log messages from edge devices."""
    
    def __init__(self, brokers: list, topic: str = "play_logs", group_id: str = "control-plane-play-logs"):
        """
        Initialize Kafka consumer.
        
        Args:
            brokers: List of Kafka broker addresses (e.g., ["10.12.58.42:9092"])
            topic: Kafka topic to consume from (default: "play_logs")
            group_id: Consumer group ID (default: "control-plane-play-logs")
        """
        self.brokers = brokers
        self.topic = topic
        self.group_id = group_id
        self.consumer = None
        self.running = False
        
    def _get_db_connection(self):
        """Create and return a PostgreSQL connection."""
        try:
            # 复用 db_service 的连接逻辑（含 .env 加载和默认值），
            # 避免消费者与 API 使用不同默认连接参数。
            conn = get_conn()
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    @staticmethod
    def _deserialize_message(raw: bytes):
        """
        Deserialize Kafka payload with encoding fallbacks.

        正常情况是 UTF-8 JSON；若历史数据或错误生产者写入了其他编码，
        这里回退到 gb18030 / latin1，尽量让消费不中断。
        """
        if raw is None:
            return {}

        last_exc = None
        for enc in ('utf-8', 'gb18030', 'latin1'):
            try:
                text = raw.decode(enc)
                return json.loads(text)
            except Exception as e:
                last_exc = e
                continue

        raise ValueError(f"Unable to deserialize kafka message, last error: {last_exc}")
    
    def _parse_timestamp(self, ts_value) -> Optional[datetime]:
        """
        Parse timestamp from various formats.
        
        Args:
            ts_value: Can be Unix timestamp (int), ISO string, or None
            
        Returns:
            datetime object or None
        """
        if ts_value is None:
            return None
            
        try:
            # If it's already a timestamp string in ISO format
            if isinstance(ts_value, str):
                # Try parsing ISO format first
                if 'T' in ts_value or ' ' in ts_value:
                    return datetime.fromisoformat(ts_value.replace('+08:00', '').replace('Z', ''))
                # If not, might be a numeric string
                return None
            
            # If it's a Unix timestamp (seconds or milliseconds)
            if isinstance(ts_value, (int, float)):
                if ts_value > 1e12:  # Likely milliseconds
                    ts_value = ts_value / 1000
                return datetime.fromtimestamp(ts_value)
                
        except Exception as e:
            logger.warning(f"Failed to parse timestamp {ts_value}: {e}")
        
        return None
    
    def _normalize_log_record(self, log_data: Dict) -> Dict:
        """
        Normalize and validate log record from Kafka message.
        
        Args:
            log_data: Raw log data from Kafka message
            
        Returns:
            Normalized log record ready for database insertion
        """
        normalized = {}
        
        # Required fields
        normalized['log_id'] = log_data.get('log_id')
        normalized['device_id'] = log_data.get('device_id')
        
        if not normalized['log_id'] or not normalized['device_id']:
            logger.warning(f"Missing required fields in log record: {log_data}")
            return None
        
        # Standard fields
        normalized['material_id'] = log_data.get('material_id') or log_data.get('ad_id')  # Support both names
        normalized['ad_file_name'] = log_data.get('ad_file_name')
        normalized['status_code'] = log_data.get('status_code')
        normalized['status_msg'] = log_data.get('status_msg')
        device_ip = log_data.get('device_ip')
        # PostgreSQL INET 字段不接受空字符串，统一转成 NULL。
        if isinstance(device_ip, str):
            device_ip = device_ip.strip()
            if not device_ip:
                device_ip = None
        normalized['device_ip'] = device_ip
        normalized['firmware_version'] = log_data.get('firmware_version')
        
        # Duration is typically in milliseconds from edge (store as INT)
        normalized['duration_ms'] = log_data.get('duration_ms')
        
        # Timestamp parsing for start/end times
        normalized['start_time'] = self._parse_timestamp(log_data.get('start_time'))
        normalized['end_time'] = self._parse_timestamp(log_data.get('end_time'))
        
        # Device-reported creation timestamp (keep as-is, should be BIGINT Unix timestamp)
        normalized['created_at'] = log_data.get('created_at')
        
        # MD5 verification fields (get from message, don't hardcode)
        normalized['expected_md5'] = log_data.get('expected_md5')
        normalized['actual_md5'] = log_data.get('actual_md5')
        normalized['is_valid'] = log_data.get('is_valid')
        billing_status = log_data.get('billing_status') or 'pending'
        if billing_status not in {'unbilled', 'billed', 'failed', 'pending'}:
            billing_status = 'pending'
        normalized['billing_status'] = billing_status
        
        return normalized
    
    def _ensure_device_exists(self, conn, device_id: str) -> bool:
        """
        Ensure device exists to satisfy ad_logs.device_id FK constraint.

        尝试最小插入 device_id；若表上还有其他非空约束导致失败，返回 False。
        """
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM devices WHERE device_id = %s LIMIT 1", (device_id,))
            if cur.fetchone():
                return True

            cur.execute(
                "INSERT INTO devices (device_id) VALUES (%s) ON CONFLICT (device_id) DO NOTHING",
                (device_id,),
            )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error("Failed to ensure device exists device_id=%s err=%s", device_id, e)
            return False
        finally:
            try:
                cur.close()
            except Exception:
                pass

    def _insert_log_record(self, conn, log_record: Dict) -> bool:
        """
        Insert or update a log record in the database using UPSERT.
        
        Args:
            conn: PostgreSQL connection
            log_record: Normalized log record
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cur = conn.cursor()

            # ad_logs.device_id 有外键约束，先确保设备存在。
            if not self._ensure_device_exists(conn, log_record.get('device_id')):
                logger.error("Skip log due to missing device FK log_id=%s device_id=%s", log_record.get('log_id'), log_record.get('device_id'))
                return False
            
            # UPSERT query (INSERT ... ON CONFLICT)
            sql = """
            INSERT INTO ad_logs (
                log_id, device_id, material_id, ad_file_name, start_time, end_time,
                duration_ms, status_code, status_msg, device_ip, firmware_version,
                created_at, expected_md5, actual_md5, is_valid, billing_status
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (log_id) DO UPDATE SET
                device_id = EXCLUDED.device_id,
                material_id = EXCLUDED.material_id,
                ad_file_name = EXCLUDED.ad_file_name,
                start_time = EXCLUDED.start_time,
                end_time = EXCLUDED.end_time,
                duration_ms = EXCLUDED.duration_ms,
                status_code = EXCLUDED.status_code,
                status_msg = EXCLUDED.status_msg,
                device_ip = EXCLUDED.device_ip,
                firmware_version = EXCLUDED.firmware_version,
                created_at = EXCLUDED.created_at,
                expected_md5 = EXCLUDED.expected_md5,
                actual_md5 = EXCLUDED.actual_md5,
                is_valid = EXCLUDED.is_valid,
                billing_status = EXCLUDED.billing_status;
            """
            
            cur.execute(sql, (
                log_record.get('log_id'),
                log_record.get('device_id'),
                log_record.get('material_id'),
                log_record.get('ad_file_name'),
                log_record.get('start_time'),
                log_record.get('end_time'),
                log_record.get('duration_ms'),
                log_record.get('status_code'),
                log_record.get('status_msg'),
                log_record.get('device_ip'),
                log_record.get('firmware_version'),
                log_record.get('created_at'),
                log_record.get('expected_md5'),
                log_record.get('actual_md5'),
                log_record.get('is_valid'),
                log_record.get('billing_status')
            ))
            
            conn.commit()
            return True
            
        except Exception as e:
            pgcode = getattr(e, 'pgcode', None)
            pgerror = getattr(e, 'pgerror', None)
            logger.error(
                "Failed to insert log record log_id=%s device_id=%s pgcode=%s err=%s pgerror=%s",
                log_record.get('log_id'),
                log_record.get('device_id'),
                pgcode,
                e,
                pgerror,
            )
            conn.rollback()
            return False
        finally:
            cur.close()
    
    def _insert_batch(self, conn, log_records: list) -> int:
        """
        Insert a batch of log records efficiently.
        
        Args:
            conn: PostgreSQL connection
            log_records: List of normalized log records
            
        Returns:
            Number of successfully inserted records
        """
        if not log_records:
            return 0
        
        success_count = 0
        for record in log_records:
            if self._insert_log_record(conn, record):
                success_count += 1
        
        logger.info(f"Batch insert: {success_count}/{len(log_records)} records inserted")
        return success_count
    
    def start_consuming(self, batch_size: int = 50):
        """
        Start consuming messages from Kafka topic and persist to database.
        
        This method sets up a Kafka consumer and continuously processes messages.
        In a production environment, this would typically run as a background service.
        
        Args:
            batch_size: Number of messages to process before committing (default: 50)
        """
        try:
            from kafka import KafkaConsumer
            from kafka.errors import KafkaError
        except ImportError:
            logger.error("kafka-python package not installed. Install with: pip install kafka-python")
            raise
        
        logger.info(f"Starting Kafka consumer for topic '{self.topic}' with group '{self.group_id}'")
        logger.info(f"Brokers: {self.brokers}")
        
        try:
            self.consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.brokers,
                group_id=self.group_id,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                max_poll_records=batch_size,
                value_deserializer=self._deserialize_message,
                session_timeout_ms=30000,
                request_timeout_ms=40000,
            )
            
            self.running = True
            batch = []
            
            logger.info("Kafka consumer started successfully, waiting for messages...")
            
            while self.running:
                try:
                    messages = self.consumer.poll(timeout_ms=1000, max_records=batch_size)
                    
                    if not messages:
                        continue
                    
                    conn = self._get_db_connection()
                    try:
                        for topic_partition, records in messages.items():
                            for message in records:
                                try:
                                    log_data = message.value
                                    logger.debug(f"Received log message: {log_data.get('log_id')}")
                                    
                                    # Check if it's a single message or batch
                                    if isinstance(log_data, dict):
                                        # Single message format or wrapped message
                                        if 'payload' in log_data:
                                            # Wrapped format with payload array
                                            payload = log_data.get('payload', [])
                                            for log_item in payload:
                                                normalized = self._normalize_log_record(log_item)
                                                if normalized:
                                                    batch.append(normalized)
                                        else:
                                            # Direct log format
                                            normalized = self._normalize_log_record(log_data)
                                            if normalized:
                                                batch.append(normalized)
                                    
                                    # Process batch when size reached
                                    if len(batch) >= batch_size:
                                        self._insert_batch(conn, batch)
                                        batch = []
                                        
                                except Exception as e:
                                    logger.error(f"Error processing message: {e}")
                                    continue
                        
                        # Process remaining messages in batch
                        if batch:
                            self._insert_batch(conn, batch)
                            batch = []
                            
                    finally:
                        conn.close()
                        
                except KafkaError as e:
                    logger.error(f"Kafka error: {e}")
                except Exception as e:
                    logger.error(f"Error in message processing loop: {e}")
                    time.sleep(5)  # Backoff before retry
        
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise
        finally:
            self.stop()
    
    def stop(self):
        """Stop the Kafka consumer."""
        self.running = False
        if self.consumer:
            try:
                self.consumer.close()
                logger.info("Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error closing Kafka consumer: {e}")


def create_consumer() -> KafkaPlayLogConsumer:
    """
    Factory function to create a Kafka consumer with configuration from environment.
    
    Returns:
        Configured KafkaPlayLogConsumer instance
    """
    # 优先使用环境变量；若未配置，回退到部署中实际可达的Kafka地址。
    # 注意：localhost 仅在“消费者和Kafka在同一台机器”时可用。
    brokers_str = os.getenv('KAFKA_BROKERS', '10.12.58.42:9092')
    brokers = [b.strip() for b in brokers_str.split(',')]
    
    topic = os.getenv('KAFKA_PLAYLOG_TOPIC', 'play_logs')
    
    return KafkaPlayLogConsumer(brokers=brokers, topic=topic)


if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start consumer
    consumer = create_consumer()
    consumer.start_consuming()
