# PII Analyzer Docker Stack Deployment Guide

**Version 2.0.0**

This guide covers deploying the PII Analyzer Docker stack to a production server. The stack provides an always-on service with a web-based control panel for analyzing files for Personally Identifiable Information (PII).

## System Requirements

| Resource | Minimum | Recommended (This Config) |
|----------|---------|---------------------------|
| CPU Cores | 8 | 32 |
| RAM | 32GB | 128GB |
| Storage | 50GB + data | 100GB + data |
| Docker | 20.10+ | 24.0+ |
| Docker Compose | 2.0+ | 2.20+ |
| Git | 2.0+ | Latest |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Apache Tika Cluster (8 instances)            │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                     │   │
│  │  │Tika 1│ │Tika 2│ │Tika 3│ │Tika 4│  ...               │   │
│  │  │ 4GB  │ │ 4GB  │ │ 4GB  │ │ 4GB  │                     │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │           Unified PII Analyzer + Dashboard                │   │
│  │                                                           │   │
│  │   • Web-based control panel (port 8080)                   │   │
│  │   • Start/Stop analysis via web UI                        │   │
│  │   • PDF report generation                                 │   │
│  │   • 28 parallel workers, 80GB RAM                         │   │
│  │   • Presidio PII detection + OCR                          │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Host Volumes                                │
│  • /data (read-only) - Data to analyze                          │
│  • ./db - SQLite database persistence                           │
│  • ./logs - Application logs                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Resource Allocation (128GB RAM / 32 Cores)

| Service | CPU | RAM | Instances |
|---------|-----|-----|-----------|
| Tika | 2 cores each | 4GB each | 8 |
| PII Analyzer + Dashboard | 28 cores | 80GB | 1 |
| **Total** | **32 cores** | **~112GB** | 9 containers |

## Deployment Steps

### 1. Install Prerequisites

Ensure Docker and Git are installed on your server:

```bash
# Check Docker version
docker --version
docker compose version

# Check Git version
git --version
```

If Docker is not installed, follow the official Docker installation guide for your OS:
https://docs.docker.com/engine/install/

### 2. Clone the Repository

```bash
# Navigate to your preferred directory
cd /home/dataadmin

# Clone the repository
git clone https://github.com/NCLGISA/pii-analyzer.git

# Enter the project directory
cd pii-analyzer
```

### 3. Prepare Directories

```bash
# Create required directories
mkdir -p db logs

# Set permissions for Docker volumes
chmod 777 db logs
```

### 4. Verify Data Mount

Ensure your data directory is accessible at `/data`:

```bash
# Check data mount
ls -la /data

# Verify Docker can access it
docker run --rm -v /data:/data:ro alpine ls /data
```

If your data is in a different location, update `docker-compose.prod.yml`:

```yaml
volumes:
  - /path/to/your/data:/data:ro  # Change this line
```

### 5. Build and Start the Stack

```bash
# Build the containers (this may take several minutes the first time)
docker compose -f docker-compose.prod.yml build

# Start the stack in detached mode
docker compose -f docker-compose.prod.yml up -d

# View startup logs
docker compose -f docker-compose.prod.yml logs -f
```

### 6. Access the Dashboard

Open in your browser: `http://YOUR_SERVER_IP:8080`

## Quick Start Script

For convenience, you can use the included quick start script:

```bash
# Make the script executable
chmod +x scripts/server-quickstart.sh

# Run the quick start
./scripts/server-quickstart.sh
```

## Using the Dashboard

### Control Panel

The dashboard includes a control panel at the top with these functions:

| Button | Description |
|--------|-------------|
| **Start Analysis** | Begin scanning and analyzing files in /data |
| **Stop Analysis** | Stop the current analysis (can be resumed) |
| **Download PDF** | Generate and download a PDF report |
| **Download JSON** | Export results as JSON |
| **Clear Results** | Delete all analysis results and start fresh |

### Workflow

1. **Place data in /data** on the Docker host
2. **Click "Start Analysis"** in the dashboard
3. **Monitor progress** in real-time on the dashboard
4. **Review results** when analysis completes
5. **Download report** as PDF or JSON
6. **Clear results** when ready to analyze new data

## Updating the Stack

To update to the latest version:

```bash
# Navigate to the project directory
cd /home/dataadmin/pii-analyzer

# Pull the latest changes
git pull origin main

# Rebuild containers
docker compose -f docker-compose.prod.yml build

# Restart the stack
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

## Management Commands

### Start/Stop the Stack

```bash
# Start all services
docker compose -f docker-compose.prod.yml up -d

# Stop all services (preserves data)
docker compose -f docker-compose.prod.yml down

# Restart the stack
docker compose -f docker-compose.prod.yml restart

# Stop and remove volumes (DELETES DATA)
docker compose -f docker-compose.prod.yml down -v
```

### View Logs

```bash
# All logs
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f pii-analyzer

# Last 100 lines
docker compose -f docker-compose.prod.yml logs --tail 100 pii-analyzer
```

### Monitor Resources

```bash
# Check container status
docker compose -f docker-compose.prod.yml ps

# Monitor resource usage
docker stats
```

## Performance Tuning

### Adjusting Worker Count

Edit environment variables in `docker-compose.prod.yml`:

```yaml
environment:
  - PII_WORKERS=24  # Reduce if experiencing memory pressure
  - PII_BATCH_SIZE=50  # Reduce for large files
```

Then restart:

```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

### Scaling Tika Instances

For document-heavy workloads, you can add more Tika instances by copying the tika service definitions in `docker-compose.prod.yml` and updating the `TIKA_SERVER_ENDPOINTS` environment variable.

### Memory Optimization

If processing many large files:

1. Reduce `PII_WORKERS` to 20-24
2. Reduce `PII_BATCH_SIZE` to 50
3. Increase Tika memory if seeing extraction failures

## Troubleshooting

### Common Issues

**1. Out of Memory Errors**

```bash
# Check which container is using memory
docker stats

# Reduce worker count in docker-compose.prod.yml
# Then restart:
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

**2. Tika Connection Errors**

```bash
# Check Tika health
docker compose -f docker-compose.prod.yml ps
docker logs pii-tika-1

# Restart Tika cluster
docker compose -f docker-compose.prod.yml restart tika1 tika2 tika3 tika4 tika5 tika6 tika7 tika8
```

**3. Dashboard Not Loading**

```bash
# Check dashboard logs
docker logs pii-analyzer

# Verify container is running
docker compose -f docker-compose.prod.yml ps

# Restart if needed
docker compose -f docker-compose.prod.yml restart pii-analyzer
```

**4. Slow Processing**

- Check if files require OCR (scanned PDFs are much slower)
- Monitor CPU and memory with `docker stats`
- Consider increasing Tika instances for document-heavy workloads

**5. Permission Errors**

```bash
# Ensure db and logs directories are writable
chmod 777 db logs

# Restart the container
docker compose -f docker-compose.prod.yml restart pii-analyzer
```

**6. Git Clone Issues**

```bash
# If you get SSL certificate errors
git config --global http.sslVerify false

# If you need to use a different branch
git checkout branch-name
```

## Security Considerations

1. **Cloudflare Zero Trust**: This stack is designed to be used behind Cloudflare Zero Trust for authentication

2. **Data Access**: The data volume is mounted read-only to prevent accidental modifications

3. **Network Isolation**: All containers communicate on an isolated Docker network

4. **Non-root Containers**: Application containers run as non-root users

## Cleanup

To completely remove the deployment:

```bash
# Stop and remove containers
docker compose -f docker-compose.prod.yml down

# Remove images
docker compose -f docker-compose.prod.yml down --rmi all

# Remove volumes (DELETES ALL DATA)
docker compose -f docker-compose.prod.yml down -v

# Clean up Docker system
docker system prune -a

# Remove the project directory (optional)
cd ..
rm -rf pii-analyzer
```
