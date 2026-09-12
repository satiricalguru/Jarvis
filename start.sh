#!/bin/bash

# Define colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}"
echo "===================================================="
echo "          🤖  JARVIS SYSTEM INITIALIZATION  🤖"
echo "===================================================="
echo -e "${NC}"

BACKEND_PID=""
FRONTEND_PID=""

# Function to clean up background processes on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down JARVIS services...${NC}"
    trap - SIGINT SIGTERM # Prevent infinite loops
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill "$FRONTEND_PID" 2>/dev/null
    fi
    # Also clean up ports if processes linger
    if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
        kill -9 $(lsof -t -i:8000) 2>/dev/null || true
    fi
    if lsof -Pi :5173 -sTCP:LISTEN -t >/dev/null 2>&1; then
        kill -9 $(lsof -t -i:5173) 2>/dev/null || true
    fi
    exit 0
}

# Trap Ctrl+C (SIGINT) and SIGTERM to run cleanup
trap cleanup SIGINT SIGTERM

# Check if port 8000 is already in use
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}Port 8000 (Backend) is already in use. Cleaning up...${NC}"
    kill -9 $(lsof -t -i:8000) 2>/dev/null || true
    sleep 1
fi

# Check if port 5173 is already in use
if lsof -Pi :5173 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}Port 5173 (Frontend) is already in use. Cleaning up...${NC}"
    kill -9 $(lsof -t -i:5173) 2>/dev/null || true
    sleep 1
fi

# Ensure .env exists in backend
if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        echo -e "${YELLOW}backend/.env not found. Creating from .env.example...${NC}"
        cp backend/.env.example backend/.env
    else
        touch backend/.env
    fi
fi

# Start Backend
echo -e "${GREEN}[1/2] Starting Backend (FastAPI)...${NC}"
cd backend
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
else
    echo -e "${YELLOW}Virtualenv not detected. Creating backend/.venv...${NC}"
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
fi

python3 -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# Wait a brief moment to let backend start initializing
sleep 1.5

# Start Frontend
echo -e "${GREEN}[2/2] Starting Frontend (Vite)...${NC}"
cd frontend
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Frontend node_modules not found. Installing dependencies...${NC}"
    npm install
fi

npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo -e "${CYAN}----------------------------------------------------"
echo -e "🚀 JARVIS online!"
echo -e "   - Backend:  http://localhost:8000"
echo -e "   - Frontend: http://localhost:5173 (or check logs below)"
echo -e "💡 Press Ctrl+C at any time to shut down both servers cleanly."
echo -e "----------------------------------------------------${NC}"

# Wait for background jobs to finish
wait

