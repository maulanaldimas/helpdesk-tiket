# Contributing to Sokkafiber Helpdesk

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## Development Setup

### Prerequisites
- Python 3.12+
- PostgreSQL 16 (or use Docker)
- Git

### Local Setup

```bash
# 1. Fork and clone the repository
git clone https://github.com/maulanaldimas/helpdesk-tiket.git
cd helpdesk-tiket

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment
cp .env.example .env
# Edit .env with your local settings

# 5. Run migrations
python manage.py migrate

# 6. Create superuser
python manage.py createsuperuser

# 7. Run development server
python manage.py runserver
```

### Docker Setup

```bash
cp .env.example .env
# Set DB_PASSWORD in .env
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

## Running Tests

Always run the full test suite before submitting a PR:

```bash
python manage.py test tickets --verbosity=2
```

All 113 tests must pass. If you add new features, include corresponding tests.

## Code Style

- Follow PEP 8 conventions
- Use meaningful variable and function names
- Keep functions focused and concise
- Add docstrings for complex logic
- No inline comments unless absolutely necessary

## Branch Naming

- `feature/description` — new features
- `fix/description` — bug fixes
- `docs/description` — documentation changes

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all tests pass: `python manage.py test tickets`
4. Push your branch and create a pull request
5. Describe your changes clearly in the PR description

## Reporting Issues

When reporting bugs, please include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Python/Django version
- Browser (if UI-related)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
