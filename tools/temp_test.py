import redis


def list_registered_devices(redis_host='localhost', redis_port=6379, redis_db=0):
	r = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)

	try:
		ids = list(r.smembers('registered_devices') or [])
	except Exception as e:
		print('Failed to read registered_devices set from Redis:', e)
		return

	if not ids:
		print('No registered devices found in Redis (registered_devices set empty).')
		return

	for did in ids:
		try:
			token = r.get(f'auth:{did}')
			info = r.hgetall(f'device:info:{did}') or {}
			print('device_id:', did)
			print('  token :', token)
			if info:
				print('  info  :')
				for k, v in info.items():
					print(f'    {k}: {v}')
			print('-' * 40)
		except Exception as e:
			print(f'Error fetching info for {did}:', e)


if __name__ == '__main__':
	# 可通过环境变量或命令行参数扩展，这里使用默认本地 Redis
	list_registered_devices()