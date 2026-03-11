# clear_redis.py
import redis
r = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)
print('before registered:', r.smembers('registered_devices'))
r.delete('registered_devices')
for pattern in ('auth:*','device:info:*','device:online:*'):
    for k in r.keys(pattern):
        print('DEL', k); r.delete(k)
print('after registered:', r.smembers('registered_devices'))