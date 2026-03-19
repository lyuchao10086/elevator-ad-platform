"""
Background task management for control-plane services.

This module manages long-running background tasks like the Kafka consumer,
ensuring they start with the application and gracefully shut down.
"""

import logging
import threading
import time
from typing import Optional
from app.services.kafka_consumer import create_consumer, KafkaPlayLogConsumer

logger = logging.getLogger(__name__)


class BackgroundTaskManager:
    """Manages background tasks like Kafka consumer."""
    
    _instance: Optional['BackgroundTaskManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the background task manager."""
        if not hasattr(self, '_initialized'):
            self.kafka_consumer: Optional[KafkaPlayLogConsumer] = None
            self.kafka_thread: Optional[threading.Thread] = None
            self.running = False
            self._initialized = True
    
    def start_kafka_consumer(self) -> bool:
        """
        Start the Kafka consumer in a background thread.
        
        Returns:
            True if consumer started successfully, False if already running or error
        """
        if self.running:
            logger.warning("Kafka consumer is already running")
            return False
        
        try:
            logger.info("Starting Kafka consumer in background thread...")
            
            # Create consumer
            self.kafka_consumer = create_consumer()
            
            # Start consumer in a daemon thread
            self.kafka_thread = threading.Thread(
                target=self._run_kafka_consumer,
                daemon=True,
                name="KafkaConsumerThread"
            )
            self.kafka_thread.start()
            
            self.running = True
            logger.info("Kafka consumer thread started")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            self.running = False
            return False
    
    def _run_kafka_consumer(self):
        """Run the Kafka consumer (executed in background thread)."""
        try:
            if self.kafka_consumer:
                self.kafka_consumer.start_consuming()
        except Exception as e:
            logger.error(f"Kafka consumer error: {e}")
            self.running = False
    
    def stop_kafka_consumer(self):
        """Stop the running Kafka consumer."""
        if self.kafka_consumer and self.running:
            logger.info("Stopping Kafka consumer...")
            self.kafka_consumer.stop()
            
            # Wait for thread to join (max 5 seconds)
            if self.kafka_thread:
                self.kafka_thread.join(timeout=5)
            
            self.running = False
            logger.info("Kafka consumer stopped")
    
    def is_running(self) -> bool:
        """Check if background tasks are running."""
        return self.running


def get_task_manager() -> BackgroundTaskManager:
    """Get the singleton task manager instance."""
    return BackgroundTaskManager()
