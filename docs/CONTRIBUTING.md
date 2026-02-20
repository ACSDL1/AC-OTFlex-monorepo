# Contributing Guide

Thank you for your interest in contributing to AC_OTFlex_Workflow! This document provides guidelines for contributing to the project.

## Code of Conduct

- Be respectful and professional
- Support collaboration and knowledge sharing
- Report issues constructively
- Focus on improving the system

## How to Contribute

### Reporting Issues

1. **Check existing issues** - Avoid duplicates
2. **Clear description** - Explain the problem clearly
3. **Steps to reproduce** - Provide reproducible steps
4. **Expected behavior** - What should happen
5. **Actual behavior** - What actually happened
6. **System info** - OS, Python version, hardware

**Example issue:**
```
Title: Cannot connect to Opentrons Flex on IP 169.254.179.32

Description:
When attempting to run test_opentrons.py, the connection attempt times out.

Steps to reproduce:
1. Run: python tests/test_opentrons.py --ip 169.254.179.32 --test connection
2. Wait for timeout

Expected: Connection succeeds
Actual: Connection timeout after 30 seconds

Environment:
- OS: Windows 10
- Python: 3.10.5
- Robot: Opentrons Flex
- IP: 169.254.179.32 (confirmed with ping)
```

### Submitting Pull Requests

1. **Fork the repository**
   ```bash
   git clone https://github.com/your-username/AC_OTFlex_Workflow.git
   cd AC_OTFlex_Workflow
   ```

2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make changes** following the code style guidelines

4. **Test your changes**
   ```bash
   python tests/run_all_tests.py --dry-run
   ```

5. **Commit with clear messages**
   ```bash
   git commit -m "Add feature: clear description of changes"
   ```

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Submit pull request** with description of changes

## Code Style

### Python Style Guide

Follow PEP 8 with these additions:

- **Line length:** 100 characters max (except long strings/URLs)
- **Indentation:** 4 spaces (no tabs)
- **Imports:** Group standard library, third-party, local (in that order)
- **Functions:** Use type hints where possible

**Example:**
```python
from pathlib import Path
from typing import Dict, Any, Optional
import json
import logging

from requests import Session  # Third-party

from src.config_manager import get_config  # Local


def process_workflow(
    workflow_dict: Dict[str, Any],
    config_path: Optional[Path] = None
) -> bool:
    """
    Process and validate workflow.
    
    Args:
        workflow_dict: Workflow configuration dictionary
        config_path: Optional path to configuration file
        
    Returns:
        bool: True if validation passed
        
    Raises:
        ValueError: If workflow is invalid
    """
    # Implementation
    pass
```

### Code Organization

**File structure:**
```
src/
├── core/              # Core functionality
├── adapters/          # Device adapters
├── workflows/         # Workflow execution
└── config_manager.py  # Configuration
```

**Module organization:**
- Group related functions/classes
- One main class per file (usually)
- Keep files under 500 lines when possible
- Clear separation of concerns

### Documentation

**Docstrings (Google style):**
```python
def calculate_transfer_volume(
    concentration_source: float,
    concentration_target: float,
    volume_target_mL: float
) -> float:
    """Calculate required transfer volume.
    
    Uses dilution formula: C1V1 = C2V2
    
    Args:
        concentration_source: Source concentration (mM)
        concentration_target: Target concentration (mM)
        volume_target_mL: Target volume (mL)
        
    Returns:
        float: Required volume from source (mL)
        
    Raises:
        ValueError: If concentrations are invalid
        
    Example:
        >>> calculate_transfer_volume(100, 10, 50)
        5.0
    """
    if concentration_source <= 0 or concentration_target <= 0:
        raise ValueError("Concentrations must be positive")
    
    return (concentration_target * volume_target_mL) / concentration_source
```

**Comments (only for complex logic):**
```python
# Use inline comments ONLY for non-obvious logic
# Avoid stating the obvious
for node in workflow.nodes:
    if node.id not in executed:
        # Add to queue using topological order to minimize backtracking
        queue.append((node, dependencies[node.id]))
```

## Testing Guidelines

### Writing Tests

Create test files in `tests/` directory:

```python
import pytest
from src.core.opentrons import opentronsClient

class TestOpentronsClient:
    """Test Opentrons client functionality."""
    
    @pytest.fixture
    def client(self):
        """Create test client instance."""
        return opentronsClient("169.254.179.32", strRobot="flex")
    
    def test_initialization(self, client):
        """Test client initialization."""
        assert client.robotType == "flex"
        assert client.robotIP == "169.254.179.32"
        assert client.runID is not None
    
    def test_invalid_ip(self):
        """Test connection with invalid IP."""
        with pytest.raises(ConnectionError):
            opentronsClient("999.999.999.999")
```

### Running Tests

```bash
# Run all tests
python tests/run_all_tests.py

# Run specific test
python tests/test_opentrons.py --test connection

# Dry-run mode
python tests/run_all_tests.py --dry-run

# With coverage
pytest --cov=src tests/
```

### Test Requirements

- All new features must have tests
- All bug fixes must have regression tests
- Tests must pass locally before submitting PR
- Use descriptive test names

## Development Tools

### Code Quality

**Format code:**
```bash
black src/ tests/
```

**Check style:**
```bash
flake8 src/ tests/ --max-line-length=100
```

**Type checking:**
```bash
mypy src/
```

### Pre-commit Hooks

Set up automatic formatting before commits:

```bash
# Install pre-commit
pip install pre-commit

# Create .pre-commit-config.yaml
cat > .pre-commit-config.yaml << EOF
repos:
  - repo: https://github.com/psf/black
    rev: 23.1.0
    hooks:
      - id: black
        language_version: python3.10
  - repo: https://github.com/PyCQA/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
EOF

# Install hooks
pre-commit install
```

## Adding New Features

### 1. Plan the Feature
- Discuss approach in issue
- Define clear scope
- Identify affected components

### 2. Design
- Update architecture documentation
- Design device adapter if needed
- Plan configuration changes

### 3. Implement
- Follow code style guide
- Write tests
- Update documentation
- Add example usage

### 4. Review and Refine
- Self-review code
- Run all tests
- Update CHANGELOG.md

### 5. Document
- Add docstrings
- Update README if needed
- Add usage example

## Adding a New Device

### 1. Create Device Adapter

```python
# src/adapters/new_device_adapter.py
class NewDevice:
    """Adapter for new device."""
    
    def __init__(self, device_cfg, root_dir):
        self.device_cfg = device_cfg or {}
        self.root_dir = root_dir
        # Load module
        
    async def connect(self):
        """Connect to device."""
        pass
    
    async def disconnect(self):
        """Disconnect from device."""
        pass
```

### 2. Create Device Runtime

```python
# src/core/new_device_runtime.py
def new_device_connect(config):
    """Initialize device connection."""
    pass

def new_device_operation(params):
    """Perform device operation."""
    pass
```

### 3. Add to Workflow Runner

Update `src/workflows/run_workflow.py` to handle new device type.

### 4. Add Tests

```python
# tests/test_new_device.py
def test_new_device_connection():
    pass
```

### 5. Add Documentation

- Update README.md
- Add USAGE.md examples
- Document node types
- Add configuration reference

## Version Numbering

Use semantic versioning: `MAJOR.MINOR.PATCH`

- **MAJOR:** Breaking changes
- **MINOR:** New features
- **PATCH:** Bug fixes

Example: `1.2.3` = version 1, feature release 2, bug fix 3

## Commit Messages

**Format:**
```
[TYPE] Brief description (50 chars max)

Detailed explanation if needed (72 char line wrap)

Fixes #123
Closes #456
```

**Types:**
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `style:` Code style
- `refactor:` Code refactoring
- `test:` Test additions
- `chore:` Build/dependency updates

**Examples:**
```
feat: Add support for custom labware definitions

Allows users to define custom labware formats in JSON
Validates labware against schema on load
Updates: USAGE.md with labware format documentation

Fixes #42

fix: Handle timeout on Opentrons connection

Previously would hang indefinitely on unreachable robot
Now uses 30-second timeout with proper error message
Adds test for timeout scenario

Closes #38
```

## Workflow for Bug Fixes

1. **Reproduce:** Create minimal test case
2. **Fix:** Implement smallest possible fix
3. **Test:** Ensure fix works and doesn't break others
4. **Document:** Update relevant documentation

## Workflow for Features

1. **Design:** Discuss approach in issue
2. **Implement:** Code the feature
3. **Test:** Comprehensive testing
4. **Document:** Update all relevant docs
5. **Example:** Add usage example

## Questions?

- Check existing documentation
- Look at existing code
- Review previous issues
- Ask in pull request discussions

Thank you for contributing!
