# depgraph

Python import dependency graph analyzer. Zero dependencies.

## Usage

```bash
# Scan and show all import edges
python3 depgraph.py scan ./src

# Detect circular imports
python3 depgraph.py cycles ./src

# Find orphan modules (never imported)
python3 depgraph.py orphans ./src

# Full stats: degrees, externals, top importers
python3 depgraph.py stats ./src

# Generate Graphviz DOT
python3 depgraph.py dot ./src --external -o deps.dot
```

## Features

- **AST-based parsing** — no execution, handles syntax errors gracefully
- **Cycle detection** — DFS-based circular import finder
- **Orphan detection** — finds dead/unused modules
- **Stats** — in/out degree analysis, external dependency listing
- **DOT output** — visualize with Graphviz
- **Configurable exclusions** — skip venv, __pycache__, etc.

## Philosophy

One file. Zero deps. Does one thing well.
