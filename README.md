# PII Analyzer

A high-performance system for analyzing files for Personally Identifiable Information (PII) using Microsoft Presidio, with Docker-based deployment optimized for large-scale document processing.

## Features

- **PII Detection**: Leverages Microsoft Presidio for detecting SSNs, credit cards, emails, phone numbers, and more
- **Scalable Architecture**: Distributed Apache Tika cluster for document text extraction
- **Resumable Processing**: Continue from where you left off if processing is interrupted
- **Parallel Processing**: Multi-process architecture for high throughput
- **OCR Support**: Tesseract OCR for scanned documents and images
- **Web Dashboard**: Real-time monitoring of analysis progress and results
- **Persistent Storage**: SQLite database for tracking processing state and results
- **Docker Deployment**: Production-ready containerized stack

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Apache Tika Cluster (8 instances)            │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                     │   │
│  │  │Tika 1│ │Tika 2│ │Tika 3│ │Tika 4│  ...               │   │
│  │  └──────┘ └──────┘ └──────┘ └──────┘                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    PII Analyzer                           │   │
│  │   • Parallel worker processes                             │   │
│  │   • Presidio PII detection                                │   │
│  │   • OCR support via Tesseract                             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Dashboard (Flask)                      │   │
│  │                    Port 8080                              │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Data directory accessible to Docker

### Deployment

1. **Clone and prepare:**

```bash
git clone https://github.com/yourusername/pii-analyzer.git
cd pii-analyzer
mkdir -p db logs
cp env.prod.example .env
```

2. **Configure environment (optional):**

```bash
# Edit .env to set a dashboard password
nano .env
```

3. **Build and start:**

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

4. **Access the dashboard:**

Open `http://localhost:8080` in your browser.

## Configuration

### Environment Variables

Copy `env.prod.example` to `.env` and customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `DASHBOARD_PASSWORD` | (none) | Password to protect dashboard access |
| `PII_WORKERS` | 28 | Number of parallel worker processes |
| `PII_BATCH_SIZE` | 100 | Batch size for processing |
| `PII_THRESHOLD` | 0.7 | Confidence threshold for PII detection (0.0-1.0) |
| `PII_FILE_SIZE_LIMIT` | 100 | Maximum file size in MB |
| `LOG_LEVEL` | INFO | Logging verbosity |

### Resource Allocation (128GB RAM / 32 Cores)

The default configuration is optimized for a 128GB RAM / 32-core server:

| Service | CPU | RAM | Instances |
|---------|-----|-----|-----------|
| Tika | 2 cores each | 4GB each | 8 |
| PII Analyzer | 28 cores | 80GB | 1 |
| Dashboard | 2 cores | 2GB | 1 |

For smaller servers, reduce worker count and Tika instances in `docker-compose.prod.yml`.

## Usage

### Analyzing Data

Mount your data directory at `/data` on the Docker host. The analyzer will automatically scan and process all files.

```bash
# Start analysis
docker compose -f docker-compose.prod.yml up -d

# View progress
docker logs -f pii-analyzer
```

### Resume After Interruption

The analyzer automatically resumes from where it left off:

```bash
docker compose -f docker-compose.prod.yml up -d pii-analyzer
```

### Export Results

```bash
docker compose -f docker-compose.prod.yml run --rm pii-analyzer \
    python -m src.process_files \
    --db-path /app/db/pii_results.db \
    --export /app/db/results.json
```

### Check Status

```bash
docker compose -f docker-compose.prod.yml run --rm pii-analyzer \
    python -m src.process_files \
    --db-path /app/db/pii_results.db \
    --status
```

### Clear Results and Re-analyze

```bash
docker compose -f docker-compose.prod.yml stop pii-analyzer
rm -rf db/*
docker compose -f docker-compose.prod.yml up -d pii-analyzer
```

## Supported File Types

The analyzer processes documents using Apache Tika for text extraction:

| Category | Extensions |
|----------|------------|
| Documents | PDF, DOCX, DOC, ODT, RTF, TXT |
| Spreadsheets | XLSX, XLS, ODS, CSV |
| Presentations | PPTX, PPT, ODP |
| Email | EML, MSG, MBOX |
| Archives | ZIP, TAR, GZ (contents extracted) |
| Images (OCR) | PNG, JPG, JPEG, TIFF, BMP |

## PII Types Detected

Using Microsoft Presidio, the analyzer detects:

- Social Security Numbers (SSN)
- Credit Card Numbers
- Email Addresses
- Phone Numbers
- Names (PERSON)
- Addresses (LOCATION)
- IP Addresses
- Dates of Birth
- Driver's License Numbers
- Passport Numbers
- And more...

## Project Structure

```
pii-analyzer/
├── src/
│   ├── analyzers/          # Presidio PII detection
│   ├── anonymizers/        # PII redaction (optional)
│   ├── core/               # File discovery & worker management
│   ├── database/           # SQLite persistence
│   ├── extractors/         # Tika text extraction & OCR
│   └── utils/              # Logging & file utilities
├── dashboard/              # Flask web dashboard
├── tests/                  # Unit tests
├── scripts/                # Deployment helper scripts
├── Dockerfile.prod         # PII Analyzer container
├── Dockerfile.dashboard    # Dashboard container
├── docker-compose.prod.yml # Production stack
└── env.prod.example        # Environment template
```

## Monitoring

### Container Status

```bash
docker compose -f docker-compose.prod.yml ps
```

### Resource Usage

```bash
docker stats
```

### Logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# Specific service
docker compose -f docker-compose.prod.yml logs -f pii-analyzer
```

## Troubleshooting

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed troubleshooting guidance covering:

- Out of memory errors
- Tika connection issues
- Dashboard problems
- Performance optimization

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
