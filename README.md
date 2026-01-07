# PII Analyzer

**Version 2.0.0**

A high-performance system for analyzing files for Personally Identifiable Information (PII) using Microsoft Presidio, with an always-on Docker-based deployment and web-based control panel.

## Features

- **Web-Based Control Panel**: Start/stop analysis, monitor progress, and download reports via web UI
- **PII Detection**: Leverages Microsoft Presidio for detecting SSNs, credit cards, emails, phone numbers, and more
- **PDF Reports**: Generate comprehensive PDF reports with executive summary and detailed findings
- **Scalable Architecture**: Distributed Apache Tika cluster for document text extraction
- **Resumable Processing**: Continue from where you left off if processing is interrupted
- **Parallel Processing**: Multi-process architecture for high throughput
- **OCR Support**: Tesseract OCR for scanned documents and images
- **Real-time Monitoring**: Dashboard shows live progress and statistics
- **Always-On Service**: Permanent stack ready to analyze new datasets on demand

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
│  │           Unified PII Analyzer + Dashboard                │   │
│  │   • Web control panel (port 8080)                         │   │
│  │   • Start/Stop/Monitor analysis                           │   │
│  │   • PDF & JSON report generation                          │   │
│  │   • Parallel worker processes                             │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Git
- Data directory mounted at `/data` on the Docker host

### Deployment

1. **Clone the repository:**

```bash
git clone https://github.com/NCLGISA/pii-analyzer.git
cd pii-analyzer
```

2. **Prepare directories:**

```bash
mkdir -p db logs
chmod 777 db logs
```

3. **Build and start:**

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
```

4. **Access the dashboard:**

Open `http://localhost:8080` in your browser.

### Quick Start Script

Alternatively, run the quick start script:

```bash
chmod +x scripts/server-quickstart.sh
./scripts/server-quickstart.sh
```

## Usage

### Web-Based Workflow

1. **Place your data** in `/data` on the Docker host
2. **Open the dashboard** at `http://localhost:8080`
3. **Click "Start Analysis"** to begin scanning
4. **Monitor progress** in real-time
5. **Download reports** when complete (PDF or JSON)
6. **Click "Clear Results"** when ready for new dataset

### Control Panel Features

| Button | Description |
|--------|-------------|
| **Start Analysis** | Scan and analyze all files in /data |
| **Stop Analysis** | Interrupt current analysis (resumable) |
| **Download PDF** | Generate comprehensive PDF report |
| **Download JSON** | Export raw results as JSON |
| **Clear Results** | Delete all results for fresh analysis |

## Updating

To update to the latest version:

```bash
cd pii-analyzer
git pull origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PII_WORKERS` | 28 | Number of parallel worker processes |
| `PII_BATCH_SIZE` | 100 | Batch size for processing |
| `PII_THRESHOLD` | 0.7 | Confidence threshold for PII detection (0.0-1.0) |
| `PII_FILE_SIZE_LIMIT` | 100 | Maximum file size in MB |
| `PII_DATA_PATH` | /data | Path to data directory inside container |

### Resource Allocation (128GB RAM / 32 Cores)

| Service | CPU | RAM | Instances |
|---------|-----|-----|-----------|
| Tika | 2 cores each | 4GB each | 8 |
| PII Analyzer + Dashboard | 28 cores | 80GB | 1 |

For smaller servers, reduce worker count and Tika instances in `docker-compose.prod.yml`.

## PDF Report Contents

The generated PDF report includes:

- **Executive Summary**: Overview of findings and risk assessment
- **Statistics**: File processing breakdown and metrics
- **Entity Analysis**: Breakdown by PII type with counts
- **High-Risk Files**: List of files containing sensitive PII (SSN, Credit Cards, etc.)
- **Detailed Findings**: Sample of detected PII with masked values

## Supported File Types

| Category | Extensions |
|----------|------------|
| Documents | PDF, DOCX, DOC, ODT, RTF, TXT |
| Spreadsheets | XLSX, XLS, ODS, CSV |
| Presentations | PPTX, PPT, ODP |
| Email | EML, MSG, MBOX |
| Archives | ZIP, TAR, GZ (contents extracted) |
| Images (OCR) | PNG, JPG, JPEG, TIFF, BMP |

## PII Types Detected

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
- Bank Account Numbers
- And more...

## Project Structure

```
pii-analyzer/
├── src/
│   ├── analyzers/          # Presidio PII detection
│   ├── anonymizers/        # PII redaction (optional)
│   ├── api/                # Analysis service API
│   ├── core/               # File discovery & worker management
│   ├── database/           # SQLite persistence
│   ├── extractors/         # Tika text extraction & OCR
│   ├── reports/            # PDF report generation
│   └── utils/              # Logging & file utilities
├── dashboard/              # Flask web dashboard
├── tests/                  # Unit tests
├── scripts/                # Deployment helper scripts
├── Dockerfile.unified      # Unified container (analyzer + dashboard)
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
