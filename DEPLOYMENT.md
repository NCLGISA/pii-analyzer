# PII Analyzer Docker Stack Deployment Guide

This guide covers deploying the PII Analyzer Docker stack to a production server optimized for high-performance processing.

## System Requirements

| Resource | Minimum | Recommended (This Config) |
|----------|---------|---------------------------|
| CPU Cores | 8 | 32 |
| RAM | 32GB | 128GB |
| Storage | 50GB + data | 100GB + data |
| Docker | 20.10+ | 24.0+ |
| Docker Compose | 2.0+ | 2.20+ |

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
│  │                    PII Analyzer                           │   │
│  │                                                           │   │
│  │   • 28 parallel workers                                   │   │
│  │   • 80GB RAM allocated                                    │   │
│  │   • Presidio PII detection                                │   │
│  │   • OCR support via Tesseract                             │   │
│  │                                                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Dashboard (Flask)                      │   │
│  │                    Port 8080                              │   │
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
| PII Analyzer | 28 cores | 80GB | 1 |
| Dashboard | 2 cores | 2GB | 1 |
| **Total** | **32 cores** | **~114GB** | 10 containers |

## Deployment Steps

### 1. Transfer Files to Server

From your local machine:

```bash
# Create a tarball of the project
tar -czvf pii-analyzer.tar.gz \
    Dockerfile.prod \
    Dockerfile.dashboard \
    docker-compose.prod.yml \
    env.prod.example \
    requirements.txt \
    src/ \
    dashboard/ \
    strict_nc_breach_pii.py \
    inspect_db.py

# Transfer to server
scp -P 2222 pii-analyzer.tar.gz dataadmin@10.11.12.222:/home/dataadmin/
```

### 2. Server Setup

SSH into the server:

```bash
ssh -p 2222 dataadmin@10.11.12.222
```

Extract and prepare:

```bash
# Navigate to working directory
cd /home/dataadmin

# Extract project files
mkdir -p pii-analyzer
tar -xzvf pii-analyzer.tar.gz -C pii-analyzer
cd pii-analyzer

# Create required directories
mkdir -p db logs

# Set up environment file
cp env.prod.example .env

# Optional: Set a dashboard password
# Edit .env and set DASHBOARD_PASSWORD=your_secure_password
```

### 3. Verify Data Mount

Ensure the data directory is accessible:

```bash
# Check data mount
ls -la /data

# Verify Docker can access it
docker run --rm -v /data:/data:ro alpine ls /data
```

### 4. Build and Start the Stack

```bash
# Build the containers
docker-compose -f docker-compose.prod.yml build

# Start the stack
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

### 5. Monitor Progress

```bash
# Check container status
docker-compose -f docker-compose.prod.yml ps

# View PII analyzer logs
docker logs -f pii-analyzer

# View dashboard logs
docker logs -f pii-dashboard

# Check resource usage
docker stats
```

### 6. Access the Dashboard

Open in browser: `http://10.11.12.222:8080`

## Management Commands

### Start/Stop the Stack

```bash
# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Stop all services (preserves data)
docker-compose -f docker-compose.prod.yml down

# Stop and remove volumes (DELETES DATA)
docker-compose -f docker-compose.prod.yml down -v
```

### Restart Analysis with New Data

```bash
# Stop the current analysis
docker-compose -f docker-compose.prod.yml stop pii-analyzer

# Optional: Clear previous results
rm -rf db/*

# Restart the analyzer
docker-compose -f docker-compose.prod.yml up -d pii-analyzer
```

### Resume Interrupted Analysis

The analyzer supports resumable processing. If interrupted:

```bash
# The analyzer will automatically resume from where it left off
docker-compose -f docker-compose.prod.yml up -d pii-analyzer

# Or explicitly resume with the --resume flag
docker-compose -f docker-compose.prod.yml run --rm pii-analyzer \
    python -m src.process_files /data \
    --db-path /app/db/pii_results.db \
    --resume \
    --workers 28
```

### Check Job Status

```bash
docker-compose -f docker-compose.prod.yml run --rm pii-analyzer \
    python -m src.process_files \
    --db-path /app/db/pii_results.db \
    --status
```

### Export Results to JSON

```bash
docker-compose -f docker-compose.prod.yml run --rm pii-analyzer \
    python -m src.process_files \
    --db-path /app/db/pii_results.db \
    --export /app/db/results.json

# Copy to host
docker cp pii-analyzer:/app/db/results.json ./results.json
```

## Performance Tuning

### Adjusting Worker Count

Edit `docker-compose.prod.yml` and modify the command:

```yaml
command: >
  python -m src.process_files
  /data
  --db-path /app/db/pii_results.db
  --workers 24  # Reduce if experiencing memory pressure
  --batch-size 50  # Reduce for large files
```

### Scaling Tika Instances

For document-heavy workloads, you can add more Tika instances by copying the tika service definitions and updating the `TIKA_SERVER_ENDPOINTS` environment variable.

### Memory Optimization

If processing many large files:

1. Reduce `--batch-size` to 25-50
2. Reduce `--workers` to 20-24
3. Increase Tika memory if seeing extraction failures

## Troubleshooting

### Common Issues

**1. Out of Memory Errors**

```bash
# Check which container is using memory
docker stats

# Reduce worker count
docker-compose -f docker-compose.prod.yml down
# Edit docker-compose.prod.yml, reduce --workers
docker-compose -f docker-compose.prod.yml up -d
```

**2. Tika Connection Errors**

```bash
# Check Tika health
docker-compose -f docker-compose.prod.yml ps
docker logs pii-tika-1

# Restart Tika cluster
docker-compose -f docker-compose.prod.yml restart tika1 tika2 tika3 tika4 tika5 tika6 tika7 tika8
```

**3. Dashboard Not Loading**

```bash
# Check dashboard logs
docker logs pii-dashboard

# Verify database exists
ls -la db/

# Restart dashboard
docker-compose -f docker-compose.prod.yml restart dashboard
```

**4. Slow Processing**

- Check if files require OCR (scanned PDFs are much slower)
- Monitor CPU and memory with `docker stats`
- Consider increasing Tika instances for document-heavy workloads

### Viewing Logs

```bash
# All logs
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f pii-analyzer

# Last 100 lines
docker-compose -f docker-compose.prod.yml logs --tail 100 pii-analyzer
```

## Security Considerations

1. **Dashboard Password**: Set `DASHBOARD_PASSWORD` in `.env` if the server is accessible from untrusted networks

2. **Data Access**: The data volume is mounted read-only to prevent accidental modifications

3. **Network Isolation**: All containers communicate on an isolated Docker network

4. **Non-root Containers**: Application containers run as non-root users

## Cleanup

To completely remove the deployment:

```bash
# Stop and remove containers
docker-compose -f docker-compose.prod.yml down

# Remove images
docker-compose -f docker-compose.prod.yml down --rmi all

# Remove volumes (DELETES ALL DATA)
docker-compose -f docker-compose.prod.yml down -v

# Clean up Docker system
docker system prune -a
```

