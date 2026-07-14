import asyncio
import time
from collections import defaultdict

class RateLimiter:
    
    def __init__(self, rate: int, per: float):
        self.rate = rate
        self.per = per
        self.allowance = defaultdict(lambda: rate)
        self.last_check = defaultdict(time.time)
    
    async def acquire(self, channel_id: int) -> None:
        current = time.time()
        time_passed = current - self.last_check[channel_id]
        self.last_check[channel_id] = current
        
        # Replenish tokens
        self.allowance[channel_id] += time_passed * (self.rate / self.per)
        
        if self.allowance[channel_id] > self.rate:
            self.allowance[channel_id] = self.rate
        
        if self.allowance[channel_id] < 1.0:
            sleep_time = (1.0 - self.allowance[channel_id]) * (self.per / self.rate)
            await asyncio.sleep(sleep_time)
            self.allowance[channel_id] = 0.0
        else:
            self.allowance[channel_id] -= 1.0