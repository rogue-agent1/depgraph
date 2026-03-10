#!/usr/bin/env python3
"""depgraph — Python import dependency graph analyzer.

Zero dependencies. Parses Python files for imports, builds a dependency
graph, detects cycles, finds orphans, and outputs DOT/JSON/text.

Usage:
    depgraph.py scan <path> [--exclude venv,__pycache__]
    depgraph.py cycles <path>
    depgraph.py orphans <path>
    depgraph.py stats <path>
    depgraph.py dot <path> [--external] [--output graph.dot]
"""

import argparse
import ast
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def find_python_files(root: str, exclude: list[str]) -> list[Path]:
    """Find all .py files under root, excluding specified dirs."""
    root_path = Path(root).resolve()
    files = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in exclude and not d.startswith('.')]
        for f in filenames:
            if f.endswith('.py'):
                files.append(Path(dirpath) / f)
    return files


def module_name(filepath: Path, root: Path) -> str:
    """Convert file path to dotted module name."""
    rel = filepath.resolve().relative_to(root.resolve())
    parts = list(rel.parts)
    if parts[-1] == '__init__.py':
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]  # strip .py
    return '.'.join(parts) if parts else '__root__'


def extract_imports(filepath: Path) -> list[str]:
    """Parse a Python file and extract all imported module names."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except (SyntaxError, ValueError):
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split('.')[0])
    return list(set(imports))


def build_graph(root: str, exclude: list[str]) -> tuple[dict, set[str], dict]:
    """Build dependency graph. Returns (graph, all_modules, file_map)."""
    root_path = Path(root).resolve()
    files = find_python_files(root, exclude)

    # Map top-level package names to local modules
    local_packages = set()
    file_map = {}
    for f in files:
        mod = module_name(f, root_path)
        top = mod.split('.')[0]
        local_packages.add(top)
        file_map[mod] = str(f)

    graph = defaultdict(set)
    all_modules = set()

    for f in files:
        mod = module_name(f, root_path)
        all_modules.add(mod)
        imports = extract_imports(f)
        for imp in imports:
            graph[mod].add(imp)

    return dict(graph), all_modules, file_map


def find_cycles(graph: dict) -> list[list[str]]:
    """Find all cycles using DFS."""
    visited = set()
    rec_stack = set()
    path = []
    cycles = []

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, set()):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                # Found cycle
                idx = path.index(neighbor)
                cycles.append(path[idx:] + [neighbor])

        path.pop()
        rec_stack.discard(node)

    for node in graph:
        if node not in visited:
            dfs(node)

    return cycles


def find_orphans(graph: dict, all_modules: set) -> list[str]:
    """Find modules that nothing imports."""
    imported = set()
    for deps in graph.values():
        imported.update(deps)

    # Modules that exist but are never imported (and aren't __main__ entry points)
    orphans = []
    for mod in sorted(all_modules):
        top = mod.split('.')[0]
        if top not in imported and mod not in imported:
            orphans.append(mod)
    return orphans


def cmd_scan(args):
    exclude = [e.strip() for e in args.exclude.split(',')] if args.exclude else ['venv', '__pycache__', 'node_modules', '.git', 'env']
    graph, all_modules, _ = build_graph(args.path, exclude)

    print(f"📦 Scanned: {args.path}")
    print(f"   Modules: {len(all_modules)}")
    print(f"   Edges:   {sum(len(v) for v in graph.values())}")
    print()

    for mod in sorted(graph):
        deps = sorted(graph[mod])
        if deps:
            print(f"  {mod} → {', '.join(deps)}")


def cmd_cycles(args):
    exclude = [e.strip() for e in args.exclude.split(',')] if args.exclude else ['venv', '__pycache__', 'node_modules', '.git', 'env']
    graph, _, _ = build_graph(args.path, exclude)
    cycles = find_cycles(graph)

    if not cycles:
        print("✅ No circular imports detected.")
        return

    # Deduplicate cycles
    seen = set()
    unique = []
    for c in cycles:
        key = tuple(sorted(c[:-1]))
        if key not in seen:
            seen.add(key)
            unique.append(c)

    print(f"🔄 Found {len(unique)} circular import{'s' if len(unique) != 1 else ''}:")
    for i, cycle in enumerate(unique, 1):
        print(f"  {i}. {' → '.join(cycle)}")


def cmd_orphans(args):
    exclude = [e.strip() for e in args.exclude.split(',')] if args.exclude else ['venv', '__pycache__', 'node_modules', '.git', 'env']
    graph, all_modules, _ = build_graph(args.path, exclude)
    orphans = find_orphans(graph, all_modules)

    if not orphans:
        print("✅ No orphan modules found.")
        return

    print(f"🏚️  Found {len(orphans)} orphan module{'s' if len(orphans) != 1 else ''} (never imported):")
    for mod in orphans:
        print(f"  • {mod}")


def cmd_stats(args):
    exclude = [e.strip() for e in args.exclude.split(',')] if args.exclude else ['venv', '__pycache__', 'node_modules', '.git', 'env']
    graph, all_modules, _ = build_graph(args.path, exclude)

    # Degree analysis
    in_degree = defaultdict(int)
    out_degree = defaultdict(int)
    external = set()

    for mod, deps in graph.items():
        out_degree[mod] = len(deps)
        for d in deps:
            in_degree[d] += 1
            top = d.split('.')[0]
            if top not in {m.split('.')[0] for m in all_modules}:
                external.add(d)

    cycles = find_cycles(graph)
    orphans = find_orphans(graph, all_modules)

    # Most imported
    top_imported = sorted(in_degree.items(), key=lambda x: -x[1])[:10]
    # Most dependencies
    top_deps = sorted(out_degree.items(), key=lambda x: -x[1])[:10]

    print(f"📊 Dependency Stats: {args.path}")
    print(f"  Local modules:    {len(all_modules)}")
    print(f"  External deps:    {len(external)}")
    print(f"  Total edges:      {sum(len(v) for v in graph.values())}")
    print(f"  Circular imports: {len(set(tuple(sorted(c[:-1])) for c in cycles))}")
    print(f"  Orphan modules:   {len(orphans)}")
    print()

    if external:
        print(f"  📦 External dependencies: {', '.join(sorted(external)[:20])}")
        print()

    if top_imported:
        print("  🏆 Most imported:")
        for mod, count in top_imported[:5]:
            print(f"    {mod}: {count} imports")
        print()

    if top_deps:
        print("  🔗 Most dependencies:")
        for mod, count in top_deps[:5]:
            print(f"    {mod}: {count} deps")


def cmd_dot(args):
    exclude = [e.strip() for e in args.exclude.split(',')] if args.exclude else ['venv', '__pycache__', 'node_modules', '.git', 'env']
    graph, all_modules, _ = build_graph(args.path, exclude)

    local_tops = {m.split('.')[0] for m in all_modules}

    lines = ['digraph dependencies {', '  rankdir=LR;', '  node [shape=box, style=filled, fillcolor="#e8e8e8"];']

    for mod in sorted(graph):
        for dep in sorted(graph[mod]):
            top = dep.split('.')[0]
            if not args.external and top not in local_tops:
                continue
            color = "#ff6666" if top not in local_tops else "#66cc66"
            lines.append(f'  "{mod}" -> "{dep}";')

    lines.append('}')
    output = '\n'.join(lines)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"📄 DOT graph written to {args.output}")
    else:
        print(output)


def main():
    parser = argparse.ArgumentParser(description="depgraph — Python dependency graph analyzer")
    sub = parser.add_subparsers(dest="cmd")

    for name in ['scan', 'cycles', 'orphans', 'stats', 'dot']:
        p = sub.add_parser(name)
        p.add_argument("path", help="Root directory to scan")
        p.add_argument("--exclude", default="venv,__pycache__,node_modules,.git,env", help="Dirs to exclude")

    sub.choices['dot'].add_argument("--external", action="store_true", help="Include external deps")
    sub.choices['dot'].add_argument("--output", "-o", help="Output file")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    {'scan': cmd_scan, 'cycles': cmd_cycles, 'orphans': cmd_orphans, 'stats': cmd_stats, 'dot': cmd_dot}[args.cmd](args)


if __name__ == "__main__":
    main()
