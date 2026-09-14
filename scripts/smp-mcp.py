#!/usr/bin/env python3
"""Serve bounded local workspace tools using newline-delimited MCP over stdio."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from socialmediaplus.mcp import serve

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    serve(args.root.expanduser().resolve())
