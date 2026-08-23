
"""
Enhanced Professional Streamlit Dashboard
Displays real-time market data with TradingView-style charts
"""
import streamlit as st
import asyncio
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
import json
import sys
import os

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.core.state_manager import StateManager
from src.core.message_bus import MessageBus
from src.agents.data_agent import DataCollectionAgent
from src.utils.config import get_config

# Page config - MUST be first Streamlit command
st.set_page_config(
    page_title="Crypto Trading Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .stMetric {
        background-color: #1e1e1e;
        padding: 10px;
        border-radius: 5px;
    }
    .metric-positive {
        color: #00ff00 !important;
    }
    .metric-negative {
        color: #ff0000 !important;
    }
    div[data-testid="stMetricValue"] {
        font-size: 24px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'system_initialized' not in st.session_state:
    try:
        config = get_config()
        state_manager = StateManager()
        message_bus = MessageBus(config.database.redis_url)
        data_agent = DataCollectionAgent(message_bus, state_manager)

        st.session_state.config = config
        st.session_state.state_manager = state_manager
        st.session_state.message_bus = message_bus
        st.session_state.data_agent = data_agent
        st.session_state.system_initialized = True
        st.session_state.agent_started = False
    except Exception as e:
        st.error(f"❌ Failed to initialize system: {e}")
        st.stop()

# Start data agent
if not st.session_state.get('agent_started', False):
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(st.session_state.state_manager.connect())
        loop.run_until_complete(st.session_state.message_bus.connect())
        loop.run_until_complete(st.session_state.data_agent.start())
        st.session_state.agent_started = True
    except Exception as e:
        st.error(f"❌ Failed to start data collection: {e}")
        st.stop()

# Helper functions
def get_live_market_data(symbol: str) -> Dict[str, Any]:
    """Get market data synchronously"""
    data_agent = st.session_state.data_agent
    
    # Get all candle data
    candles_data = {}
    if symbol in data_agent.candle_buffers:
        for tf in st.session_state.config.trading.timeframes:
            candles_data[tf] = data_agent.candle_buffers[symbol].get(tf, [])
    
    # Get live price data
    live_price = data_agent.live_price_data.get(symbol)
    
    # Get order book
    order_book = data_agent.order_book_data.get(symbol)
    
    # Get funding rate (synchronous wrapper)
    try:
        loop = asyncio.get_event_loop()
        funding_rate = loop.run_until_complete(
            st.session_state.state_manager.get(f"funding_rate:{symbol}")
        )
    except:
        funding_rate = None
    
    return {
        'symbol': symbol,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'candles': candles_data,
        'order_book': order_book,
        'funding_rate': funding_rate or {'rate': 0, 'timestamp': datetime.now(timezone.utc).isoformat()},
        'live_price': live_price
    }

def create_professional_chart(df: pd.DataFrame, symbol: str, timeframe: str) -> go.Figure:
    """Create TradingView-style chart with advanced features"""

    # Work on a copy to avoid SettingWithCopyWarning
    df = df.copy()

    # Calculate indicators for better visualization
    df['ma20'] = df['close'].rolling(window=20).mean()
    df['ma50'] = df['close'].rolling(window=50).mean()
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(f'{symbol} - {timeframe}', 'Volume'),
        row_heights=[0.7, 0.3]
    )
    
    # Candlestick
    fig.add_trace(
        go.Candlestick(
            x=df['timestamp'],
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350'
        ),
        row=1, col=1
    )
    
    # Moving averages
    fig.add_trace(
        go.Scatter(
            x=df['timestamp'],
            y=df['ma20'],
            name='MA20',
            line=dict(color='#2196F3', width=1),
            opacity=0.7
        ),
        row=1, col=1
    )
    
    fig.add_trace(
        go.Scatter(
            x=df['timestamp'],
            y=df['ma50'],
            name='MA50',
            line=dict(color='#FF9800', width=1),
            opacity=0.7
        ),
        row=1, col=1
    )
    
    # Volume bars with color coding
    colors = ['#26a69a' if close >= open else '#ef5350' 
              for close, open in zip(df['close'], df['open'])]
    
    fig.add_trace(
        go.Bar(
            x=df['timestamp'],
            y=df['volume'],
            name='Volume',
            marker_color=colors,
            opacity=0.5
        ),
        row=2, col=1
    )
    
    # Update layout for professional look
    fig.update_layout(
        height=700,
        template='plotly_dark',
        xaxis_rangeslider_visible=False,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        margin=dict(l=50, r=50, t=50, b=50)
    )
    
    # Update axes
    fig.update_xaxes(
        title_text="Time",
        row=2, col=1,
        gridcolor='#2a2a2a',
        showgrid=True
    )
    
    fig.update_yaxes(
        title_text="Price (USDT)",
        row=1, col=1,
        gridcolor='#2a2a2a',
        showgrid=True
    )
    
    fig.update_yaxes(
        title_text="Volume",
        row=2, col=1,
        gridcolor='#2a2a2a',
        showgrid=True
    )
    
    return fig

# Main UI
st.title("📊 Professional Crypto Trading Dashboard")
st.caption("Real-time market data with TradingView-style charts")

# Sidebar
with st.sidebar:
    st.header("⚙️ Dashboard Settings")
    
    config = st.session_state.config
    selected_symbol = st.selectbox(
        "Trading Pair",
        config.trading.symbols,
        index=0
    )
    
    selected_timeframe = st.selectbox(
        "Timeframe",
        config.trading.timeframes,
        index=0
    )
    
    st.divider()
    
    st.subheader("📈 Display Options")
    show_ma = st.checkbox("Show Moving Averages", value=True)
    candle_count = st.slider("Candles to Display", 50, 500, 100)
    
    st.divider()
    
    st.subheader("🔄 Auto Refresh")
    auto_refresh = st.checkbox("Enable Auto Refresh", value=True)
    if auto_refresh:
        refresh_interval = st.slider("Refresh Rate (seconds)", 1, 10, 2)
    
    st.divider()
    
    # Connection status
    st.subheader("🔌 System Status")
    if st.session_state.agent_started:
        st.success("🟢 Connected")
    else:
        st.error("🔴 Disconnected")
    
    # Data agent stats
    data_agent = st.session_state.data_agent
    if selected_symbol in data_agent.candle_buffers:
        total_candles = sum(
            len(data_agent.candle_buffers[selected_symbol].get(tf, []))
            for tf in config.trading.timeframes
        )
        st.metric("Total Candles", f"{total_candles:,}")

# Get market data
market_data = get_live_market_data(selected_symbol)

# Top metrics row
col1, col2, col3, col4 = st.columns(4)

with col1:
    # Live price from ticker
    if market_data['live_price']:
        price = market_data['live_price']['price']
        change_pct = market_data['live_price']['change_percent']
        st.metric(
            "💰 Current Price",
            f"${price:,.2f}",
            f"{change_pct:+.2f}%",
            delta_color="normal"
        )
    else:
        st.metric("💰 Current Price", "Loading...")

with col2:
    # 24h Volume
    if market_data['live_price']:
        volume = market_data['live_price']['volume']
        st.metric("📊 24h Volume", f"{volume:,.0f}")
    else:
        st.metric("📊 24h Volume", "Loading...")

with col3:
    # Funding rate
    funding_rate = market_data['funding_rate']['rate']
    st.metric("💸 Funding Rate", f"{funding_rate:.4%}")

with col4:
    # Order book spread
    if market_data['order_book']:
        ob = market_data['order_book']
        if ob.get('best_bid') and ob.get('best_ask'):
            spread = ob['best_ask'] - ob['best_bid']
            spread_pct = (spread / ob['best_bid']) * 100
            st.metric("📖 Spread", f"{spread_pct:.3f}%")
    else:
        st.metric("📖 Spread", "Loading...")

st.divider()

# Main chart
candles = market_data['candles'].get(selected_timeframe, [])

if candles and len(candles) > 0:
    # Convert to DataFrame
    df = pd.DataFrame(candles)
    
    # Ensure timestamp is datetime
    if 'timestamp' in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Sort by timestamp
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Get last N candles for display
    df_display = df.tail(candle_count)
    
    # Create chart
    fig = create_professional_chart(df_display, selected_symbol, selected_timeframe)
    
    # Display chart
    st.plotly_chart(fig, width='stretch', key=f"chart_{selected_timeframe}")
    
    # Chart info
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"📊 Displaying {len(df_display)} of {len(df)} total candles")
    with col2:
        if len(df) > 0:
            latest = df.iloc[-1]
            st.info(f"🕐 Latest: {latest['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
    with col3:
        if len(df) > 0:
            oldest = df_display.iloc[0]
            st.info(f"🕐 Oldest: {oldest['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
else:
    st.warning(f"⏳ Waiting for {selected_timeframe} candle data...")
    st.info("💡 Data is being collected from Binance. This may take a few moments.")

# Order book section
st.divider()
st.subheader("📋 Order Book Depth")

if market_data['order_book']:
    ob = market_data['order_book']
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🟢 Bids (Buy Orders)")
        if ob['bids']:
            bids_df = pd.DataFrame(ob['bids'][:10], columns=['Price', 'Quantity'])
            bids_df['Total'] = (bids_df['Price'] * bids_df['Quantity']).cumsum()
            bids_df['Price'] = bids_df['Price'].apply(lambda x: f"${x:,.2f}")
            bids_df['Quantity'] = bids_df['Quantity'].apply(lambda x: f"{x:.4f}")
            bids_df['Total'] = bids_df['Total'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(bids_df, width='stretch', hide_index=True)
    
    with col2:
        st.markdown("### 🔴 Asks (Sell Orders)")
        if ob['asks']:
            asks_df = pd.DataFrame(ob['asks'][:10], columns=['Price', 'Quantity'])
            asks_df['Total'] = (asks_df['Price'] * asks_df['Quantity']).cumsum()
            asks_df['Price'] = asks_df['Price'].apply(lambda x: f"${x:,.2f}")
            asks_df['Quantity'] = asks_df['Quantity'].apply(lambda x: f"{x:.4f}")
            asks_df['Total'] = asks_df['Total'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(asks_df, width='stretch', hide_index=True)
    
    # Order book summary
    if ob.get('best_bid') and ob.get('best_ask'):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Best Bid", f"${ob['best_bid']:,.2f}")
        with col2:
            st.metric("Best Ask", f"${ob['best_ask']:,.2f}")
        with col3:
            spread = ob['best_ask'] - ob['best_bid']
            st.metric("Spread", f"${spread:.2f}")
else:
    st.info("⏳ Waiting for order book data...")

# Recent trades table
st.divider()
st.subheader("🕐 Recent Candles")

if candles and len(candles) > 0:
    recent_df = df.tail(20).copy()
    recent_df['timestamp'] = recent_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    recent_df['change'] = ((recent_df['close'] - recent_df['open']) / recent_df['open'] * 100).round(2)
    
    # Format columns
    display_df = recent_df[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'change']].copy()
    display_df.columns = ['Time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Change %']
    
    # Reverse to show newest first
    display_df = display_df.iloc[::-1].reset_index(drop=True)
    
    st.dataframe(
        display_df,
        width='stretch',
        hide_index=True,
        column_config={
            "Change %": st.column_config.NumberColumn(
                "Change %",
                format="%.2f%%"
            )
        }
    )

# Multi-timeframe view
st.divider()
st.subheader("📊 Multi-Timeframe Analysis")

cols = st.columns(len(config.trading.timeframes))

for idx, tf in enumerate(config.trading.timeframes):
    with cols[idx]:
        tf_candles = market_data['candles'].get(tf, [])
        if tf_candles and len(tf_candles) > 0:
            latest = tf_candles[-1]
            prev = tf_candles[-2] if len(tf_candles) > 1 else latest
            
            change = latest['close'] - prev['close']
            change_pct = (change / prev['close']) * 100
            
            st.metric(
                f"{tf}",
                f"${latest['close']:,.2f}",
                f"{change_pct:+.2f}%"
            )
        else:
            st.metric(f"{tf}", "Loading...")

# Footer
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    st.caption(f"🕐 Last updated: {datetime.now().strftime('%H:%M:%S')}")
with col2:
    st.caption("📡 Data source: Binance Futures")
with col3:
    st.caption("⚡ WebSocket: Live")

# Auto refresh
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()