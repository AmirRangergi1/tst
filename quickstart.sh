#!/bin/bash
# Quick Start Guide for pdf-to-excel

set -e  # Exit on error

echo "🚀 pdf-to-excel Quick Start"
echo "============================"
echo ""

# Check if Docker is available
if command -v docker &> /dev/null; then
    echo "✓ Docker found"
    echo ""
    echo "Starting with Docker Compose..."
    echo "Building containers..."
    docker-compose build
    echo ""
    echo "🚀 Starting services..."
    docker-compose up -d
    echo ""
    echo "⏳ Waiting for services to start..."
    sleep 5
    echo ""
    echo "✅ Services started!"
    echo ""
    echo "📱 Access the application:"
    echo "   Web UI: http://localhost/static/index.html"
    echo "   API Docs: http://localhost/docs (if Nginx proxies it)"
    echo "   Health: http://localhost/health"
    echo ""
    echo "📋 Logs:"
    echo "   docker-compose logs -f web"
    echo ""
else
    echo "❌ Docker not found. Installing dependencies locally..."
    echo ""
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo "❌ Python 3 not found. Please install Python 3.11+"
        exit 1
    fi
    
    echo "✓ Python found"
    echo ""
    
    # Create venv
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    echo "✓ Virtual environment created"
    echo ""
    
    # Install deps
    echo "Installing dependencies (this may take a few minutes)..."
    pip install -q -r requirements.txt
    echo "✓ Dependencies installed"
    echo ""
    
    # Start server
    echo "🚀 Starting FastAPI server..."
    echo ""
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi
