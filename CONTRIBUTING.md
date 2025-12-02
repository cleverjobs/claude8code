# Contributing to claude8code

Thank you for your interest in contributing to claude8code! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (for Claude Code CLI)
- Docker (optional, for integration testing)

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/krisjobs/claude8code.git
   cd claude8code
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   ```

3. Install Claude Code CLI:
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude /login  # Authenticate with your Claude account
   ```

4. Run the development server:
   ```bash
   claude8code --reload --debug
   ```

## Code Style

We use the following tools to maintain code quality:

- **Ruff** - Linting and formatting
- **MyPy** - Type checking
- **Pytest** - Testing

### Running Quality Checks

```bash
# Lint code
make lint

# Format code
make format

# Type check
mypy src/

# Run all checks
make lint && mypy src/
```

### Style Guidelines

- Follow PEP 8 conventions
- Use type hints for all function signatures
- Keep functions focused and under 50 lines when possible
- Write docstrings for public functions and classes
- Use meaningful variable names

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make coverage

# Run specific test file
pytest tests/test_models.py -v

# Run tests matching a pattern
pytest -k "test_streaming" -v
```

### Writing Tests

- Place tests in the `tests/` directory
- Name test files with `test_` prefix
- Use fixtures from `conftest.py` for common setup
- Mock external dependencies (especially Claude API)

### Testing Without Claude API

For contributors without Claude API access, tests use mocked responses:

```bash
USE_CLAUDE_MOCK=true pytest
```

The mock fixtures in `conftest.py` provide realistic responses for testing.

## Pull Request Process

1. **Fork the repository** and create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the code style guidelines

3. **Add tests** for any new functionality

4. **Run quality checks**:
   ```bash
   make lint
   mypy src/
   pytest
   ```

5. **Commit your changes** with a descriptive message:
   ```bash
   git commit -m "Add feature: brief description"
   ```

6. **Push to your fork** and open a Pull Request

### PR Guidelines

- Provide a clear description of the changes
- Reference any related issues
- Ensure all CI checks pass
- Keep PRs focused on a single feature or fix
- Update documentation if needed

## Reporting Issues

### Bug Reports

When reporting a bug, please include:

- Python and Node.js versions
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages or logs

### Feature Requests

For feature requests, please describe:

- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Questions?

If you have questions about contributing, feel free to:

- Open a GitHub issue
- Check existing issues for similar questions

Thank you for contributing!
