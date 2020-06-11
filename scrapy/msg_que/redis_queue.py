
import redis
import random
import pickle
from scrapy.utils.reqser import request_from_dict
from scrapy.utils.python import to_unicode
from .serialize import serial_output,get_object


class Fifo_queue_(object):
    
    #temp values 
    host='localhost'
    port=6379
    db=0
    password=None
    socket_timeout=None

    def __init__ (self,*args, **kwargs):
        #super().__init__(name=None, **kwargs)
        self.redis_conn=self.connect_redis(
            self.host, 
            self.port, 
            self.db, 
            self.password,
            self.socket_timeout
        )
        self.state=-1 # -1 for uninitiated, 1 for in run , 0 for end
        self.name="scrapy_data"
   
    def connect_redis(self, host, port, db, password,socket_timeout):
        #creates connection with the redis in-memory database
        r =redis.Redis(host, port, db, password,socket_timeout)
        return r 
    
    def push(self, request):
        #it inserts request url into the quque of redis database
        key= random.getrandbits(32)
        item=serial_output(request)
        j=self.redis_conn.hset(name=self.name,
                             key=key,
                             value=item)        
        return key

    def pop(self):
        #Releases item in the top of the queue (since fifo)  
        #or else returns 0 if nothing is left in que
        key_cur=self.redis_conn.hkeys(self.name)
        if key_cur:
            temp= self.redis_conn.hget(self.name,key_cur[0])
            self.redis_conn.hdel(self.name,key_cur[0])
            return get_object(temp)
        else :
            self.state=0
            return None
    
    def __len__(self):
        return len(self.redis_conn.hkeys(self.name))

    def close(self):
        pass

    def run(self):
        #it initates the retrieving of requests from redis
        if self.state== -1:
            self.state = 1
            while self.state==1:
                yield self.pop()
        else :
            "Queue has already been processed or being processed"            
    

class Lifo_queue_(Fifo_queue_):
    def pop(self):
        #Releases item in the bottom of the queue (since Lifo)  
        #or else returns None if nothing is left in que
        key_cur=self.redis_conn.hkeys(self.name)
        if key_cur:
            temp= self.redis_conn.hget(self.name,key_cur[-1])
            self.redis_conn.hdel(self.name,key_cur[-1])
            return get_object(temp)
        else :
            self.state=0
            return None


#Following initation code is kept for temporary testing,
# later it will removed from here

class Fifo_queue_disk(Fifo_queue_):
    def __init__(self,key,*args, **kwargs):
        self.name=key
        super(Fifo_queue_disk, self).__init__(*args, **kwargs)

    def push(self, request):
        #it inserts request url into the quque of redis database
        key= random.getrandbits(32)
        item=pickle.dumps(request)
        j=self.redis_conn.hset(name=self.name,
                             key=123,
                             value=item)        
        return key

    def pop(self):
        #Releases item in the top of the queue (since fifo)  
        #or else returns 0 if nothing is left in que
        key_cur=self.redis_conn.hkeys(self.name)
        if key_cur:
            temp= self.redis_conn.hget(self.name,key_cur[0])
            self.redis_conn.hdel(self.name,key_cur[0])
            return pickle.loads(temp)
        else :
            self.state=0
            return None


class Lifo_queue_disk(Fifo_queue_disk):
    def pop(self):
        #Releases item in the bottom of the queue (since Lifo)  
        #or else returns None if nothing is left in que
        key_cur=self.redis_conn.hkeys(self.name)
        if key_cur:
            temp= self.redis_conn.hget(self.name,key_cur[-1])
            self.redis_conn.hdel(self.name,key_cur[-1])
            return pickle.loads(temp)
        else :
            self.state=0
            return None


