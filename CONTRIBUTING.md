# Contributing to OrbitFlow 2.0

Thank you for your interest in contributing to OrbitFlow! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, inclusive, and professional in all interactions.

## Getting Started

### 1. Fork and Clone

```bash
# Fork the repository on GitHub
# Clone your fork
git clone https://github.com/yourusername/orbitflow.git
cd orbitflow

# Add upstream remote
git remote add upstream https://github.com/originalauthor/orbitflow.git
```

### 2. Create a Branch

```bash
# Update your local main
git checkout main
git pull upstream main

# Create a feature branch
git checkout -b feature/your-feature-name
```

### 3. Set Up Development Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest pytest-cov black flake8

# Install pre-commit hooks (optional)
pip install pre-commit
pre-commit install
```

## Development Workflow

### Code Style

We follow PEP 8 and use Black for formatting.

```bash
# Format code
black traffic/ bridge/ digital_twin/ bam/ scenarios/ audit/ dashboard/

# Check style
flake8 traffic/ bridge/ digital_twin/ bam/ scenarios/ audit/ dashboard/
```

### Writing Tests

All new features must include tests.

```python
# Example test structure
import pytest
from traffic.features import build_features

def test_feature_extraction():
    """Test that features are extracted correctly."""
    obs = {
        "rate_obs": np.ones(19),
        "q_rt": np.ones(19),
        "q_nrt": np.ones(19),
        "los": np.ones(19),
        "elev": np.ones(19),
        "prev_lit": np.zeros(19),
        "prev_power": np.ones(19) * 50,
        "guard": MockGuardState(),
        "emergency": np.zeros(19),
        "t": 0,
        "ssb": 0,
        "sib": 0,
    }
    
    features = build_features(obs)
    assert features.shape == (19, 19)
    assert not np.isnan(features).any()
```

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_channel.py -v

# With coverage
python -m pytest tests/ --cov=. --cov-report=html

# Fast mode (exclude slow tests)
python -m pytest tests/ -m "not slow"
```

### Documentation

Update documentation for all public APIs.

```python
def predict_window(self, rate_hist: np.ndarray) -> np.ndarray:
    """
    Predict demand for next 3 slots given history.
    
    Args:
        rate_hist: (N, W) historical demand array
                   where N = num cells, W = window size
    
    Returns:
        predictions: (N, 3) predicted demands for next 3 slots
        
    Raises:
        ValueError: If rate_hist shape is invalid
        
    Example:
        >>> rate_hist = np.random.randn(19, 12)
        >>> pred = model.predict_window(rate_hist)
        >>> pred.shape
        (19, 3)
    """
```

## Types of Contributions

### Bug Fixes

1. Create an issue describing the bug
2. Reference the issue in your PR
3. Include a test that reproduces the bug
4. Fix the bug and verify tests pass

```bash
# Example PR title
git commit -m "Fix: Prevent NaN in feature normalization (fixes #42)"
```

### New Features

1. Discuss the feature in an issue first
2. Implement the feature with tests
3. Update documentation
4. Create a PR with clear description

```bash
# Example PR title and description
# Title: Feature: Add attention visualization to dashboard

# Description:
# - Implements attention weight extraction from BRIDGE agent
# - Visualizes attention as heatmap on dashboard
# - Includes tests and documentation
# - Closes #123
```

### Documentation

1. Improve existing docs
2. Add examples or tutorials
3. Fix typos and clarifications

### Performance Improvements

1. Benchmark current performance
2. Implement optimization
3. Verify performance gain
4. Include benchmarks in PR

## Commit Guidelines

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style (formatting, missing semicolons, etc.)
- `refactor`: Code refactoring without feature changes
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `ci`: CI/CD configuration
- `chore`: Maintenance tasks

### Examples

```bash
git commit -m "feat: Add attention visualization to agent"
git commit -m "fix: Prevent NaN in queue calculation"
git commit -m "docs: Add feature engineering guide"
git commit -m "perf: Vectorize event filtering loop"
```

## Pull Request Process

### Before Submitting

1. **Update code**
   - All tests pass: `pytest tests/ -v`
   - Code formatted: `black .`
   - No linting issues: `flake8 .`

2. **Update documentation**
   - Docstrings for new functions
   - README if needed
   - Architecture docs if significant changes

3. **Add tests**
   - New features have tests
   - Tests pass locally
   - Coverage maintained or improved

4. **Commit messages**
   - Clear, descriptive messages
   - Reference issues when relevant
   - Follow conventional commits

### Submitting PR

1. Push branch to your fork
2. Create PR on GitHub
3. Fill out PR template completely
4. Link related issues
5. Request reviewers

### PR Template

```markdown
## Description
Brief description of changes.

## Related Issues
Closes #123

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Performance improvement

## Testing
Describe testing performed:
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing on [platform]

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] No new warnings generated
- [ ] Tests added/updated
- [ ] Tests pass locally

## Screenshots
For UI changes, include screenshots.

## Additional Notes
Any additional information.
```

## Code Review Process

### What Reviewers Look For

- ✅ Code quality and style
- ✅ Test coverage
- ✅ Documentation
- ✅ Performance implications
- ✅ Security considerations
- ✅ Breaking changes

### Addressing Feedback

1. Make requested changes
2. Commit with clear message: `fix review feedback`
3. Don't force push unless requested
4. Respond to comments
5. Re-request review

## Project Structure

```
orbitflow/
├── traffic/              # Phase 3: Prediction
├── bridge/              # Phase 4: RL Agent
├── digital_twin/        # Phase 1: Twin
├── bam/                 # Phase 1: Policy
├── scenarios/           # Phase 2: Events
├── dashboard/           # Phase 5: UI
├── tests/               # Test suite
├── data/                # Data files
├── models/              # Model checkpoints
├── results/             # Training results
└── docs/                # Documentation
```

## Important Files

- `requirements.txt` - Python dependencies
- `config.yaml` - Global configuration
- `docker-compose.yml` - Docker setup
- `pytest.ini` - Test configuration

## Testing Requirements

### Test Coverage

- Minimum 80% code coverage
- All public APIs tested
- Edge cases covered
- Error conditions tested

### Test Organization

```
tests/
├── test_channel.py          # Phase 1: Channel tests
├── test_twin.py             # Phase 1: Twin tests
├── test_guard.py            # Phase 1: Guard tests
├── test_events.py           # Phase 2: Event tests
├── test_no_leakage.py       # Phase 2: Leakage tests
└── conftest.py              # Shared fixtures
```

## Documentation Standards

### Docstrings

```python
def function_name(arg1: Type1, arg2: Type2) -> ReturnType:
    """
    Brief one-line description.
    
    Longer description explaining what the function does,
    why it's useful, and any important details.
    
    Args:
        arg1: Description of arg1
        arg2: Description of arg2
    
    Returns:
        Description of return value
        
    Raises:
        ValueError: When something is invalid
        TypeError: When wrong type provided
        
    Example:
        >>> result = function_name(1, 2)
        >>> result
        3
        
    Note:
        Any important notes about the function.
    """
```

## Performance Considerations

When contributing, consider:

- Algorithm complexity (O(n) vs O(n²))
- Memory usage (avoid unnecessary copies)
- Vectorization (use NumPy ops)
- Caching (expensive computations)
- Batch processing (for ML)

## Security Considerations

- Never commit secrets or credentials
- Use environment variables for sensitive config
- Validate all inputs
- Sanitize external data
- Don't log sensitive information

## Release Process

### Versioning

We use Semantic Versioning: `MAJOR.MINOR.PATCH`

- `MAJOR`: Breaking changes
- `MINOR`: New features (backward compatible)
- `PATCH`: Bug fixes

### Changelog

Add entries to `CHANGELOG.md`:

```markdown
## [1.2.0] - 2026-11-01

### Added
- New feature description

### Changed
- Changed feature description

### Fixed
- Bug fix description
```

## Getting Help

- **Questions**: Open an issue with `question` label
- **Bugs**: Open an issue with `bug` label
- **Features**: Open an issue with `enhancement` label
- **Discussions**: Use GitHub Discussions
- **Documentation**: Check `/docs` directory

## Recognition

Contributors will be recognized in:
- `CONTRIBUTORS.md` file
- Release notes
- Project README

## Additional Resources

- [Python Style Guide (PEP 8)](https://www.python.org/dev/peps/pep-0008/)
- [Git Documentation](https://git-scm.com/doc)
- [GitHub Flow Guide](https://guides.github.com/introduction/flow/)
- [Conventional Commits](https://www.conventionalcommits.org/)

## Questions?

Feel free to ask in:
- [GitHub Discussions](https://github.com/yourusername/orbitflow/discussions)
- [GitHub Issues](https://github.com/yourusername/orbitflow/issues)

Thank you for contributing to OrbitFlow! 🎉
