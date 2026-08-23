const WebSocket = require('ws');

console.log('Testing WebSocket connection to ws://127.0.0.1:8000/ws...\n');

const ws = new WebSocket('ws://127.0.0.1:8000/ws');

ws.on('open', () => {
    console.log('✅ WebSocket connection SUCCESSFUL!');
    console.log('Connection is working properly.\n');
    
    // Keep connection alive for a few seconds to receive messages
    setTimeout(() => {
        console.log('Closing connection...');
        ws.close();
    }, 5000);
});

ws.on('message', (data) => {
    try {
        const parsed = JSON.parse(data);
        console.log('📨 Received message:', parsed.type || 'unknown type');
        console.log('   Data preview:', JSON.stringify(parsed).substring(0, 150) + '...\n');
    } catch (e) {
        console.log('📨 Received raw message:', data.toString().substring(0, 100) + '...\n');
    }
});

ws.on('error', (error) => {
    console.error('❌ WebSocket ERROR:', error.message);
    console.error('\nPossible causes:');
    console.error('  1. Backend server not running on port 8000');
    console.error('  2. Firewall blocking the connection');
    console.error('  3. Backend crashed or not responding\n');
    process.exit(1);
});

ws.on('close', (code, reason) => {
    console.log(`Connection closed. Code: ${code}, Reason: ${reason || 'No reason provided'}`);
    process.exit(0);
});
