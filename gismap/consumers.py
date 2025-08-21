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


class CameraStreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.camera_id = self.scope['url_route']['kwargs']['camera_id']
        await self.accept()
        print(f"[WS] Client connected to camera {self.camera_id}")

        # Start async loop to push frames
        self.task = asyncio.create_task(self.send_frames())

    async def disconnect(self, close_code):
        print(f"[WS] Client disconnected from camera {self.camera_id}")
        if hasattr(self, "task"):
            self.task.cancel()

    async def send_frames(self):
        while True:
            frame_data = redis_client.get(f"camera:{self.camera_id}:frame")
            if frame_data:
                await self.send_json({
                    "camera_id": self.camera_id,
                    "frame": frame_data.decode("utf-8")  # already base64
                })
            await asyncio.sleep(1.0)  # ~1 fps
