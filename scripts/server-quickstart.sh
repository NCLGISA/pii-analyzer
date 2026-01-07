#!/bin/bash
# Quick Start Script for PII Analyzer
# Run this script after cloning the repository
#
# Usage: ./scripts/server-quickstart.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}PII Analyzer Quick Start${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

cd "$PROJECT_DIR"

# Check prerequisites
echo -e "${BLUE}Checking prerequisites...${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker first: https://docs.docker.com/engine/install/"
    exit 1
fi
echo -e "${GREEN}✓${NC} Docker found: $(docker --version)"

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi
echo -e "${GREEN}✓${NC} Docker Compose found: $(docker compose version --short)"

# Check if user can run Docker
if ! docker ps &> /dev/null; then
    echo -e "${YELLOW}Warning: Cannot run Docker commands${NC}"
    echo "You may need to:"
    echo "  1. Add your user to the docker group: sudo usermod -aG docker \$USER"
    echo "  2. Log out and log back in"
    echo "  3. Or run this script with sudo"
    exit 1
fi
echo -e "${GREEN}✓${NC} Docker permissions OK"

echo ""

# Create required directories
echo -e "${BLUE}Creating directories...${NC}"
mkdir -p db logs
chmod 777 db logs
echo -e "${GREEN}✓${NC} Created db/ and logs/ directories"

# Check /data directory
echo ""
echo -e "${BLUE}Checking data directory...${NC}"
if [ -d "/data" ]; then
    FILE_COUNT=$(find /data -type f 2>/dev/null | head -100 | wc -l)
    echo -e "${GREEN}✓${NC} /data directory exists (found $FILE_COUNT+ files)"
else
    echo -e "${YELLOW}Warning: /data directory does not exist${NC}"
    echo "Please ensure your data is mounted at /data before starting analysis"
    echo "Or modify docker-compose.prod.yml to point to your data location"
fi

echo ""

# Build containers
echo -e "${BLUE}Building Docker containers (this may take several minutes)...${NC}"
docker compose -f docker-compose.prod.yml build

echo ""

# Start the stack
echo -e "${BLUE}Starting the PII Analyzer stack...${NC}"
docker compose -f docker-compose.prod.yml up -d

echo ""

# Wait for services to be ready
echo -e "${BLUE}Waiting for services to start...${NC}"
sleep 10

# Check container status
echo ""
echo -e "${BLUE}Container Status:${NC}"
docker compose -f docker-compose.prod.yml ps

echo ""

# Get the server IP
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

# Check if dashboard is accessible
echo -e "${BLUE}Checking dashboard...${NC}"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ | grep -q "200\|302"; then
    echo -e "${GREEN}✓${NC} Dashboard is running"
else
    echo -e "${YELLOW}Dashboard may still be starting...${NC}"
fi

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "Dashboard URL: ${BLUE}http://${SERVER_IP}:8080${NC}"
echo ""
echo "Next steps:"
echo "  1. Open the dashboard in your browser"
echo "  2. Ensure your data is in /data"
echo "  3. Click 'Start Analysis' to begin"
echo ""
echo "Useful commands:"
echo "  View logs:     docker compose -f docker-compose.prod.yml logs -f"
echo "  Stop stack:    docker compose -f docker-compose.prod.yml down"
echo "  Restart:       docker compose -f docker-compose.prod.yml restart"
echo ""
