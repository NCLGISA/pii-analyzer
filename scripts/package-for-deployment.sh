#!/bin/bash
# Package PII Analyzer for deployment to remote server
# Usage: ./scripts/package-for-deployment.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PACKAGE_NAME="pii-analyzer-deploy-$(date +%Y%m%d-%H%M%S).tar.gz"

echo "================================================"
echo "PII Analyzer Deployment Packager"
echo "================================================"
echo ""

cd "$PROJECT_DIR"

echo "Creating deployment package: $PACKAGE_NAME"
echo ""

# Create the tarball with all necessary files
tar -czvf "$PACKAGE_NAME" \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='*.egg-info' \
    --exclude='.pytest_cache' \
    --exclude='*.db' \
    --exclude='logs/*' \
    --exclude='db/*' \
    Dockerfile.prod \
    Dockerfile.dashboard \
    docker-compose.prod.yml \
    env.prod.example \
    DEPLOYMENT.md \
    requirements.txt \
    src/ \
    dashboard/ \
    strict_nc_breach_pii.py \
    inspect_db.py

echo ""
echo "================================================"
echo "Package created: $PACKAGE_NAME"
echo "Size: $(du -h "$PACKAGE_NAME" | cut -f1)"
echo "================================================"
echo ""
echo "To deploy to server:"
echo ""
echo "  1. Transfer the package:"
echo "     scp -P 2222 $PACKAGE_NAME dataadmin@10.11.12.222:/home/dataadmin/"
echo ""
echo "  2. SSH to server and extract:"
echo "     ssh -p 2222 dataadmin@10.11.12.222"
echo "     cd /home/dataadmin"
echo "     mkdir -p pii-analyzer && tar -xzvf $PACKAGE_NAME -C pii-analyzer"
echo "     cd pii-analyzer"
echo ""
echo "  3. Set up and run:"
echo "     mkdir -p db logs"
echo "     cp env.prod.example .env"
echo "     docker-compose -f docker-compose.prod.yml build"
echo "     docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo "  4. Access dashboard at: http://10.11.12.222:8080"
echo ""
echo "See DEPLOYMENT.md for full documentation."
echo ""

