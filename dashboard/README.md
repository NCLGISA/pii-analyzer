# PII Analysis Dashboard

A Flask web application that provides real-time visualization of PII analysis progress and results.

## Features

- Progress monitoring for PII analysis jobs
- File type statistics and charts
- Entity type statistics and charts
- High-risk file identification
- Error analysis and categorization
- Mobile-responsive design
- Auto-refreshing data
- Optional password protection

## Screenshots

(Add screenshots once the dashboard is running)

## Usage with Docker (Recommended)

The dashboard is deployed as part of the PII Analyzer Docker stack:

```bash
# Start the full stack (includes dashboard on port 8080)
docker compose -f docker-compose.prod.yml up -d

# Access the dashboard
open http://localhost:8080
```

See the main [README.md](../README.md) for full deployment instructions.

## Standalone Development

### Requirements

- Python 3.6+
- Flask and dependencies (see requirements.txt)
- Access to a PII analysis database

### Installation

```bash
pip install -r requirements.txt
```

### Running

```bash
# Default database path
python app.py

# Custom database path
python app.py --db-path=/path/to/your/pii_results.db

# With password protection
python app.py --password your_secure_password

# Or via environment variable
DASHBOARD_PASSWORD=your_secure_password python app.py
```

Access the dashboard at: `http://localhost:5000`

## Project Structure

```
dashboard/
├── app.py                 # Flask application
├── templates/             # HTML templates
│   ├── index.html         # Main dashboard template
│   └── login.html         # Login page (password protection)
├── static/                # Static files
│   ├── css/               # CSS stylesheets
│   │   └── dashboard.css  # Dashboard styles
│   ├── js/                # JavaScript files
│   │   └── dashboard.js   # Dashboard functionality
│   └── img/               # Images and icons
│       └── logo.svg       # Dashboard logo
└── README.md              # This file
```

## Development

The dashboard is built with:

- Flask backend
- Bootstrap 5 CSS framework
- Chart.js for data visualization
- JavaScript for interactivity

## License

This project is part of the PII Analyzer system.
