"""WebSocket consumers. Echo is a smoke target — kept after VehicleAll
(6d) lands so isolated WS connectivity can still be verified."""
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class EchoConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive_json(self, content):
        await self.send_json({"echo": content})

    async def disconnect(self, code):
        pass
