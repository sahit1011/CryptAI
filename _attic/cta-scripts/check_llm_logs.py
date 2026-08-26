import subprocess
import sys

# Run the test and capture output
result = subprocess.run(
    [sys.executable, "test_realtime_analysis.py"],
    capture_output=True,
    text=True,
    cwd=r"c:\Users\krish\OneDrive\Desktop\multi-agent-crypto-quant-system\crypto-trading-agent"
)

# Combine stdout and stderr
output = result.stdout + result.stderr

# Search for LLM-related lines
keywords = ["Attempting", "🤖", "LLM", "refinement", "OpenRouter", "Groq", "Claude", "client not initialized", "client initialized"]

print("=" * 80)
print("LLM REFINEMENT LOGS")
print("=" * 80)

for line in output.split('\n'):
    if any(keyword in line for keyword in keywords):
        print(line)

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

# Check for success indicators
if "🤖 Attempting" in output:
    print("✅ LLM refinement was attempted")
else:
    print("❌ LLM refinement was NOT attempted")

if "LLM unavailable or failed, using computational setup" in output:
    print("❌ LLM refinement failed - fell back to computational")
else:
    print("✅ LLM refinement did NOT fall back to computational")

if "OpenRouter raw response" in output or "Groq raw response" in output:
    print("✅ LLM response received successfully")
else:
    print("⚠️  No LLM response detected in logs")
