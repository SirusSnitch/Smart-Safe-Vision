# gismap/consumers.py
import json
import asyncio
import base64
import redis.asyncio as aioredis
from channels.generic.websocket import AsyncWebsocketConsumer

# Async Redis client
redis_client = aioredis.from_url("redis://localhost:6379")

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

        # Start async loop to push annotated frames
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
                # Get latest annotated frame from Redis (raw JPEG bytes)
                key = f"frame:{self.camera_id}:detection"
                jpeg_bytes = await redis_client.get(key)

                if jpeg_bytes:
                    # Convert JPEG bytes -> base64 for WebSocket transport
                    frame_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")

                    await self.send_json({
                        "camera_id": self.camera_id,
                        "frame": frame_b64
                    })

                    print(f"[WS] Sent frame for camera {self.camera_id}")

                # Adjust fps (currently 10 fps max)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            print(f"[WS] Frame loop cancelled for camera {self.camera_id}")
