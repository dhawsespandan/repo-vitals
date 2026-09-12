"""The PER_DEPENDENCY agent — §5.9's graph, and the thesis feature.

`graph.py` holds the whole of it. There is one entry point, `run`, and it is
called from exactly one place: `services.run_per_dependency`, on a background
thread, once per (scan, dependency).
"""
