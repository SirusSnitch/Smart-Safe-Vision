# consumers.py - Placez ce fichier dans votre app gismap
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from datetime import datetime

class TestConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print(f"WebSocket connection attempt from {self.scope['client']}")
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connexion WebSocket établie avec succès!',
            'timestamp': datetime.now().isoformat()
        }))
        print("WebSocket connection established")

    async def disconnect(self, close_code):
        print(f"WebSocket disconnected with code: {close_code}")

    async def receive(self, text_data):
        print(f"Received WebSocket message: {text_data}")
        
        try:
            # Essayer de parser comme JSON
            data = json.loads(text_data)
            await self.handle_json_message(data)
        except json.JSONDecodeError:
            # Si ce n'est pas du JSON, traiter comme texte simple
            await self.handle_text_message(text_data)

    async def handle_json_message(self, data):
        """Gère les messages JSON"""
        response = {
            'type': 'json_response',
            'original_message': data,
            'response': f"Message JSON reçu: {data.get('type', 'unknown')}",
            'timestamp': datetime.now().isoformat()
        }
        await self.send(text_data=json.dumps(response))

    async def handle_text_message(self, message):
        """Gère les messages texte simples"""
        response_message = ""
        
        # Réponses spécifiques pour certains messages
        if message.lower() == "hello":
            response_message = "Hello! WebSocket fonctionne parfaitement! 👋"
        elif message.lower() == "ping":
            response_message = "Pong! 🏓"
        elif message.lower() == "test":
            response_message = "Test reçu! Le WebSocket fonctionne correctement ✅"
        elif message.lower() == "time":
            response_message = f"Heure actuelle: {datetime.now().strftime('%H:%M:%S')}"
        else:
            response_message = f"Echo: {message} (message reçu à {datetime.now().strftime('%H:%M:%S')})"
        
        response = {
            'type': 'text_response',
            'message': response_message,
            'original': message,
            'timestamp': datetime.now().isoformat()
        }
        
        await self.send(text_data=json.dumps(response))