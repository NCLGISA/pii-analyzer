# Contributing to PII Analyzer

Thank you for considering contributing to PII Analyzer! This document provides guidelines for contributing to the project.

## Development Setup

### Option 1: Docker-Based Development (Recommended)

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/your-username/pii-analyzer.git
   cd pii-analyzer
   ```

2. **Prepare directories**
   ```bash
   mkdir -p db logs
   chmod 777 db logs
   ```

3. **Build and start the development stack**
   ```bash
   docker compose -f docker-compose.prod.yml build
   docker compose -f docker-compose.prod.yml up -d
   ```

4. **View logs**
   ```bash
   docker compose -f docker-compose.prod.yml logs -f
   ```

### Option 2: Local Development

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/your-username/pii-analyzer.git
   cd pii-analyzer
   ```

2. **Set up your development environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python -m spacy download en_core_web_lg
   ```

3. **Start the Tika server**
   ```bash
   docker run -d -p 9998:9998 apache/tika:2.9.1.0
   ```

4. **Run the analyzer**
   ```bash
   python -m src.process_files /path/to/data --db-path results.db
   ```

## Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes and ensure tests pass**
   ```bash
   pytest tests/
   ```

3. **Format your code**
   ```bash
   black .
   flake8
   ```

4. **Commit your changes with a descriptive message**
   ```bash
   git commit -m "Add feature: description of your changes"
   ```

5. **Push your branch and create a pull request**
   ```bash
   git push origin feature/your-feature-name
   ```

## Project Structure

```
pii-analyzer/
├── src/
│   ├── analyzers/          # PII detection (Presidio)
│   ├── anonymizers/        # PII redaction
│   ├── core/               # File discovery & worker management
│   ├── database/           # SQLite persistence
│   ├── extractors/         # Text extraction (Tika, OCR)
│   └── utils/              # Logging & file utilities
├── dashboard/              # Flask web dashboard
├── tests/                  # Unit tests
├── scripts/                # Deployment scripts
├── Dockerfile.prod         # PII Analyzer container
├── Dockerfile.dashboard    # Dashboard container
└── docker-compose.prod.yml # Production stack
```

## Adding Support for New File Types

To add support for a new file type:

1. Create a new extractor in `src/extractors/`
2. Update `extractor_factory.py` to recognize and handle the new type
3. Add tests for the new functionality
4. Update documentation

## Adding New PII Entity Types

To add detection for new PII types:

1. Create or update recognizers in `src/analyzers/presidio_analyzer.py`
2. Add tests for the new entity type
3. Update the dashboard to display the new entity type

## Pull Request Guidelines

- Keep PRs focused on a single feature or bug fix
- Write tests to cover new functionality
- Update documentation to reflect changes
- Follow the existing code style (we use Black for formatting)
- Make sure all tests pass before submitting
- Test with Docker deployment before submitting

## Testing Docker Builds

Before submitting changes that affect Docker builds:

```bash
# Build both images
docker compose -f docker-compose.prod.yml build

# Start the stack
docker compose -f docker-compose.prod.yml up -d

# Verify all containers are healthy
docker compose -f docker-compose.prod.yml ps

# Run a quick test
docker compose -f docker-compose.prod.yml logs pii-analyzer
```

## Code of Conduct

Please be respectful and inclusive in your interactions with the project. We follow a standard code of conduct that promotes a positive environment for everyone.
