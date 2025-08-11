from apscheduler.schedulers.asyncio import AsyncIOScheduler 

connected_clients = {} 
pending_requests = {}
scheduler = AsyncIOScheduler()