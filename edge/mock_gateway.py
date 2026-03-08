import asyncio
import websockets
import json
import logging
import signal

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def handler(websocket):
    client_addr = websocket.remote_address
    logging.info(f"Client connected from {client_addr}")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # 区分消息类型
                if "logs" in data:
                    # 日志上报消息
                    logs = data["logs"]
                    device_id = data.get("id", "Unknown")
                    logging.info(f"Received {len(logs)} logs from device {device_id}")
                    # for log in logs:
                    #     logging.debug(f"  Log ID: {log['log_id']}, Ad: {log['ad_file_name']}")
                        
                elif "id" in data and "token" in data and len(data) == 2:
                    # 心跳消息 (只有 id 和 token)
                    device_id = data["id"]
                    logging.info(f"Received Heartbeat from device {device_id}")
                    
                else:
                    # 其他未知消息
                    logging.info(f"Received message: {data}")

            except json.JSONDecodeError:
                logging.error(f"Received invalid JSON: {message}")
            except Exception as e:
                logging.error(f"Error processing message: {e}")

    except websockets.exceptions.ConnectionClosedOK:
        logging.info(f"Client {client_addr} disconnected normally")
    except websockets.exceptions.ConnectionClosedError:
        logging.warning(f"Client {client_addr} disconnected with error")
    except Exception as e:
        logging.error(f"Connection error: {e}")
    finally:
        logging.info(f"Connection closed for {client_addr}")

async def main():
    stop = asyncio.Future()
    loop = asyncio.get_running_loop()
    # 优雅退出
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set_result, None)

    logging.info("Starting Mock Gateway Server on ws://0.0.0.0:8080")
    async with websockets.serve(handler, "0.0.0.0", 8080, ping_interval=None):
        await stop # Run until signal received

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
