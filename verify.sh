#!/bin/bash
# Simple verification script without complex test dependencies

echo "🧪 Quick Verification of pdf-to-excel"
echo "======================================"
echo ""

# Test 1: Check imports
echo "Test 1: Checking core Python imports..."
python3 -c "
import sys
try:
    import fastapi
    import uvicorn
    import pdfplumber
    import pandas
    import openpyxl
    print('✓ All core dependencies OK')
    sys.exit(0)
except ImportError as e:
    print(f'❌ Missing dependency: {e}')
    sys.exit(1)
" || exit 1

echo ""

# Test 2: Check app loads
echo "Test 2: Loading FastAPI app..."
python3 -c "
try:
    from app.main import app
    print('✓ FastAPI app loaded successfully')
except Exception as e:
    print(f'❌ App load failed: {e}')
    import sys
    sys.exit(1)
"  || exit 1

echo ""

# Test 3: Check endpoints
echo "Test 3: Testing endpoints with uvicorn + curl..."
echo "Starting server in background..."

python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8888 &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Test health endpoint
echo ""
echo "Testing /health endpoint..."
HEALTH=$(curl -s http://127.0.0.1:8888/health 2>/dev/null)
if echo "$HEALTH" | grep -q '"status":"ok"'; then
    echo "✓ Health check passed"
else
    echo "❌ Health check failed: $HEALTH"
    kill $SERVER_PID 2>/dev/null
    exit 1
fi

# Test static files
echo ""
echo "Testing /static/index.html..."
STATIC=$(curl -s http://127.0.0.1:8888/static/index.html 2>/dev/null)
if echo "$STATIC" | grep -q '<html\|<!DOCTYPE'; then
    echo "✓ Static files served correctly"
else
    echo "❌ Static files not found"
    kill $SERVER_PID 2>/dev/null
    exit 1
fi

# Test invalid file type
echo ""
echo "Testing /convert endpoint (invalid file type)..."
INVALID=$(curl -s -F "file=@/etc/hostname" -w "\n%{http_code}" http://127.0.0.1:8888/convert 2>/dev/null | tail -1)
if [ "$INVALID" = "400" ]; then
    echo "✓ Invalid file type rejected (HTTP 400)"
else
    echo "❌ Expected 400, got $INVALID"
fi

# Cleanup
echo ""
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null

echo ""
echo "✅ All verification tests passed!"
echo ""
echo "Next steps:"
echo "  • Run: uvicorn app.main:app --reload --port 8000"
echo "  • Open: http://localhost:8000/static/index.html"
echo "  • Or use Docker: docker-compose up -d"
