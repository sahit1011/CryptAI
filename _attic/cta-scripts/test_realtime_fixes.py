#!/usr/bin/env python3
"""
Quick test script to verify real-time connectivity fixes
"""
import asyncio
import redis.asyncio as redis
import json

async def test_redis_state():
    """Test if Redis state is accessible"""
    print("🔍 Testing Redis State Access...")
    
    try:
        # Connect to Redis
        r = redis.from_url("redis://localhost:6379")
        
        # Test 1: Check portfolio state
        print("\n📊 Test 1: Portfolio State")
        portfolio = await r.get("state:portfolio")
        if portfolio:
            data = json.loads(portfolio)
            print(f"✅ Portfolio found: ${data.get('total_equity', 0):,.2f}")
            print(f"   - Initial Balance: ${data.get('initial_balance', 0):,.2f}")
            print(f"   - Current Balance: ${data.get('current_balance', 0):,.2f}")
            print(f"   - Unrealized P&L: ${data.get('unrealized_pnl', 0):+,.2f}")
        else:
            print("⚠️  No portfolio state found (expected before system starts)")
        
        # Test 2: Check positions
        print("\n📍 Test 2: Positions")
        positions = await r.lrange("state:positions", 0, -1)
        if positions:
            print(f"✅ Found {len(positions)} positions")
            for i, pos in enumerate(positions):
                pos_data = json.loads(pos)
                print(f"   Position {i+1}: {pos_data.get('symbol')} {pos_data.get('positionSide')}")
        else:
            print("✅ No positions (expected before trading starts)")
        
        # Test 3: Check current prices
        print("\n💰 Test 3: Current Prices")
        prices = await r.hgetall("state:current_prices")
        if prices:
            print(f"✅ Found {len(prices)} price entries")
            for symbol, price in prices.items():
                symbol_str = symbol.decode() if isinstance(symbol, bytes) else symbol
                price_val = json.loads(price.decode() if isinstance(price, bytes) else price)
                print(f"   {symbol_str}: ${price_val:,.2f}")
        else:
            print("⚠️  No prices found (expected before system starts)")
        
        # Test 4: Check agent states
        print("\n🤖 Test 4: Agent States")
        agent_keys = await r.keys("state:agent:*")
        if agent_keys:
            print(f"✅ Found {len(agent_keys)} agent state entries")
        else:
            print("⚠️  No agent states found (expected before system starts)")
        
        await r.close()
        
        print("\n" + "="*60)
        print("✅ Redis connectivity test completed successfully!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Error testing Redis: {e}")
        print("Make sure Redis is running: redis-server")
        return False
    
    return True

async def main():
    print("="*60)
    print("Real-time Connectivity Test")
    print("="*60)
    
    success = await test_redis_state()
    
    if success:
        print("\n✅ All tests passed!")
        print("\nNext steps:")
        print("1. Start the system: .\\start_system.ps1")
        print("2. Open frontend: http://localhost:5173")
        print("3. Verify $10,000 displays immediately")
        print("4. Refresh page and verify state persists")
    else:
        print("\n❌ Tests failed. Please check Redis connection.")

if __name__ == "__main__":
    asyncio.run(main())
