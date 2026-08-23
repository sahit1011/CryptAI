"""
Call Close Positions API
Triggers the API endpoint to cleanly close all positions
"""
import requests
import json

def call_close_api():
    try:
        print("🚀 Calling API to close positions...")
        response = requests.post("http://localhost:8000/api/close-positions")
        
        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ API Response: {json.dumps(result, indent=2)}")
            
            if result.get("success"):
                print(f"\n🎉 Successfully closed {result.get('closed_count')} position(s)")
                print(f"💰 Total Realized P&L: ${result.get('total_pnl', 0):.2f}")
            else:
                print(f"\n⚠️ API reported failure: {result.get('error')}")
        else:
            print(f"\n❌ API Error: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"\n❌ Connection Error: {e}")
        print("   Make sure the API server is running on localhost:8000")

if __name__ == "__main__":
    call_close_api()
