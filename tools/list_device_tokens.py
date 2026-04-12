import argparse
import redis


def main() -> None:
    parser = argparse.ArgumentParser(description="List device tokens from Redis auth:* keys")
    parser.add_argument("--host", default="10.12.58.42", help="Redis host")
    parser.add_argument("--port", type=int, default=6379, help="Redis port")
    parser.add_argument("--db", type=int, default=0, help="Redis DB")
    parser.add_argument("--password", default="123456", help="Redis password")
    args = parser.parse_args()

    rdb = redis.Redis(
        host=args.host,
        port=args.port,
        db=args.db,
        password=args.password,
        decode_responses=True,
    )

    keys = sorted(list(rdb.scan_iter(match="auth:*", count=1000)))
    if not keys:
        print("No auth:* keys found.")
        return

    print(f"Found {len(keys)} device token entries:")
    for key in keys:
        device_id = key.split(":", 1)[1] if ":" in key else key
        token = rdb.get(key)
        print(f"{device_id} -> {token}")


if __name__ == "__main__":
    main()
