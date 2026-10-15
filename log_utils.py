WIDTH = 70


def rule(char: str = "=") -> str:
    """Return a full-width ASCII separator line."""
    return char * WIDTH


def section(title: str) -> str:
    """Return a major section header framed with '=' rules."""
    return f"{rule('=')}\n{title}\n{rule('=')}"


def subsection(title: str) -> str:
    """Return a sub-step header framed with '-' rules."""
    return f"{rule('-')}\n{title}\n{rule('-')}"


def field(label: str, value: object, width: int = 18) -> str:
    """Return an aligned 'label : value' line."""
    return f"  {label:<{width}}: {value}"
