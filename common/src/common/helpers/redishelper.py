import redis
import os
import json
from typing import Any
from contextlib import nullcontext

class RedisHelper():

    def __init__(self, redis_config: Any = None):

        redis_config = redis_config if (redis_config and type(redis_config) == 'dict') else {}
        self.redis_config = redis_config
        self.redis_api = None

    def __enter__(self):
        try:
            host = self.redis_config.get('host', os.getenv('REDIS_HOST'))
            port = self.redis_config.get('port', int(os.getenv('REDIS_PORT')))
            db = self.redis_config.get('db', int(os.getenv('REDIS_DB')))
            
            print(f'Redis config parameters... {host}, {port}, {db}')
            self.redis_api = redis.Redis(host=host, port=port, db=db, decode_responses=True)

        except Exception as exc:
            print(f'error initializing redis: {exc}')

        return self
    
    def __exit__(self, exc_type, exc, tb):
        if self.redis_api:
            try:
                self.redis_api.close()
            except:
                pass
            self.redis_api = None
        return False
    
    def getpubsub(self):
        if self.redis_api:
            return self.redis_api.pubsub() #pubsub is a context manager
        return nullcontext #return null context manager
    
    def publish(self, channel:str, message:Any):
        if self.redis_api and channel and message:
            self.redis_api.publish(channel, json.dumps(message))

    
        