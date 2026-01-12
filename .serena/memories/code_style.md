# Code Style and Conventions

## Python
- **Style**: PEP 8 compliant, pythonic patterns
- **Docstrings**: Google Style Docstrings for all functions and classes
- **Type Hints**: Use type hints for function signatures
- **Avoid**: Go/Java/C++ patterns (e.g., don't use callables when initializing classes)

### Example
```python
def get_rig_status(rig_id: int, include_caps: bool = False) -> dict:
    """Get the current status of a rig.

    Args:
        rig_id: The index of the rig to query.
        include_caps: Whether to include capability information.

    Returns:
        A dictionary containing rig status fields.

    Raises:
        ValueError: If rig_id is out of range.
    """
    ...
```

## JavaScript
- **Style**: Modern ES6+, vanilla JS (no frameworks)
- **Documentation**: JSDoc for all functions
- **DOM**: Use helper functions `$()` and `$$()` defined in app.js

### Example
```javascript
/**
 * Set the frequency for a rig.
 * @param {number} idx - Rig index
 * @param {number} hz - Frequency in Hz
 * @returns {Promise<Object>} API response
 */
const setRigFrequency = async (idx, hz) => { ... };
```

## CSS
- Global styles in `multirig/static/style.css`
- Use CSS Grid for form layouts (`180px 1fr` pattern)
- Always use `box-sizing: border-box` on padded elements
- CSS variables for theming/colors

## Testing
- **Python tests**: `tests/` directory, pytest style
- **JS tests**: `js-tests/` directory, Jest style
- **E2E tests**: `tests/e2e/` directory, Playwright
- Profile-based test isolation for E2E tests
