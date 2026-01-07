#!/bin/bash
# Quick Start Script for PII Analyzer on Production Server
# Run this script after extracting the deployment package
#
# Usage: ./scripts/server-quickstart.sh [--password YOUR_PASSWORD]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}PII Analyzer Quick Start${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

cd "$PROJECT_DIR"

# Parse arguments
DASHBOARD_PASSWORD=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --password)
            DASHBOARD_PASSWORD="$2"
            shift 2
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Check Docker
echo -e "${YELLOW}Checking Docker installation...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker is installed${NC}"

# Check data directory
echo -e "${YELLOW}Checking /data directory...${NC}"
if [ ! -d "/data" ]; then
    echo -e "${RED}/data directory does not exist. Please mount your data directory.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ /data directory exists${NC}"

# Create required directories
echo -e "${YELLOW}Creating required directories...${NC}"
mkdir -p db logs
echo -e "${GREEN}✓ Directories created${NC}"

# Set up environment file
echo -e "${YELLOW}Setting up environment file...${NC}"
if [ ! -f ".env" ]; then
    cp env.prod.example .env
    echo -e "${GREEN}✓ Created .env from template${NC}"
else
    echo -e "${YELLOW}✓ .env already exists, skipping${NC}"
fi

# Set dashboard password if provided
if [ -n "$DASHBOARD_PASSWORD" ]; then
    echo -e "${YELLOW}Setting dashboard password...${NC}"
    if grep -q "^DASHBOARD_PASSWORD=" .env; then
        sed -i "s/^DASHBOARD_PASSWORD=.*/DASHBOARD_PASSWORD=$DASHBOARD_PASSWORD/" .env
    else
        echo "DASHBOARD_PASSWORD=$DASHBOARD_PASSWORD" >> .env
    fi
    echo -e "${GREEN}✓ Dashboard password set${NC}"
fi

# Build containers
echo ""
echo -e "${YELLOW}Building Docker containers (this may take several minutes)...${NC}"
docker-compose -f docker-compose.prod.yml build

# Start the stack
echo ""
echo -e "${YELLOW}Starting PII Analyzer stack...${NC}"
docker-compose -f docker-compose.prod.yml up -d

# Wait for services to start
echo ""
echo -e "${YELLOW}Waiting for services to start...${NC}"
sleep 10

# Check status
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

docker-compose -f docker-compose.prod.yml ps

echo ""
echo -e "${GREEN}Dashboard:${NC} http://$(hostname -I | awk '{print $1}'):8080"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo "  View logs:        docker-compose -f docker-compose.prod.yml logs -f"
echo "  Check status:     docker-compose -f docker-compose.prod.yml ps"
echo "  Stop stack:       docker-compose -f docker-compose.prod.yml down"
echo "  View analysis:    docker logs -f pii-analyzer"
echo ""

