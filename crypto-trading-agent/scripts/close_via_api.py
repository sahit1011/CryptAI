"""
Close Active Positions via API
Calls the API endpoint to close all active positions
"""
import requests
import json

API_URL = "http://localhost:8000/api/close-positions"

def close_positions():
    """Close all active positions via API"""
    
    print("=" * 70)
    print("  CLOSE ACTIVE POSITIONS VIA API")
    print("=" * 70)
    print()
    
    print("⚠️  This will close ALL active positions at current market price.")
    confirmation = input("Do you want to proceed? (yes/no): ").strip().lower()
    
    if confirmation != 'yes':
        print("❌ Operation cancelled.")
        return
    
    print("\n🔄 Sending close request to API...")
    
    try:
        response = requests.post(API_URL, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get('success'):
            closed_count = result.get('closed_count', 0)
            total_pnl = result.get('total_pnl', 0)
            message = result.get('message', '')
            
            print(f"\n✅ {message}")
            print(f"💰 Total Realized P&L: ${total_pnl:.2f}")
            
            positions = result.get('positions', [])
            if positions:
                print(f"\n📊 Closed Positions:")
                for pos in positions:
                    symbol = pos.get('symbol', 'N/A')
                    side = pos.get('side', 'N/A')
                    exit_price = pos.get('exit_price', 0)
                    realized_pnl = pos.get('realized_pnl', 0)
                    
                    print(f"  • {symbol} {side}")
                    print(f"    Exit Price: ${exit_price:.2f}")
                    print(f"    P&L: ${realized_pnl:.2f}")
                    print()
        else:
            error = result.get('error', 'Unknown error')
            print(f"\n❌ Failed to close positions: {error}")
            
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to API server.")
        print("   Make sure the trading system is running (./start_system.ps1)")
    except requests.exceptions.Timeout:
        print("\n❌ Error: Request timed out.")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    try:
        close_positions()
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user.")
