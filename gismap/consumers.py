# gismap/consumers.py
import json
import redis
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer

redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("notifications", self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard("notifications", self.channel_name)

    async def send_notification(self, event):
        message = event['data']
        await self.send(text_data=json.dumps(message))



# gismap/consumers.py

# gismap/consumers.py
import redis.asyncio as aioredis
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer

# Async Redis client
redis_client = aioredis.from_url("redis://localhost:6379")

class CameraStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.camera_id = self.scope['url_route']['kwargs']['camera_id']
        await self.accept()
        print(f"[WS] Client connected to camera {self.camera_id}")
        self.task = asyncio.create_task(self.send_frames())

    async def disconnect(self, close_code):
        print(f"[WS] Client disconnected from camera {self.camera_id}")
        if hasattr(self, "task"):
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def send_frames(self):
        try:
            while True:
                # Get latest JPEG bytes from Redis
                frame_data = await redis_client.get(f"camera:{self.camera_id}:frame")
                if frame_data:
                    # 🔑 Send raw binary instead of JSON
                    await self.send(bytes_data=frame_data)

                await asyncio.sleep(1/15)  # ~15 fps
        except asyncio.CancelledError:
            print(f"[WS] Frame sending loop cancelled for camera {self.camera_id}")
