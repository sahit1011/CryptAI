import asyncio
import websockets
import json

async def test_connection():
    uri = "ws://127.0.0.1:8000/ws"
    print(f"Attempting to connect to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected successfully!")
            
            # Wait for initial state
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received message: {message[:100]}...")
            except asyncio.TimeoutError:
                print("⚠️ Timed out waiting for initial message")
            
    except ConnectionRefusedError:
        print("❌ Connection Refused: The server is not accepting connections on this port.")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())
