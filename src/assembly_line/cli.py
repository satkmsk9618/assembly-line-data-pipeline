"""Command line entry point for the assembly-line pipeline."""
import argparse
import logging
from pathlib import Path

from assembly_line.generate import generate
from assembly_line.transform import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the assembly line demo pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="make sample raw machine exports")
    gen.add_argument("--vehicles", type=int, default=1000)
    gen.add_argument("--seed", type=int, default=7)
    gen.add_argument("--output", type=Path, default=Path("data/raw"))
    run = sub.add_parser("run", help="clean exports and calculate metrics")
    run.add_argument("--raw", type=Path, default=Path("data/raw"))
    run.add_argument("--processed", type=Path, default=Path("data/processed"))
    run.add_argument("--takt", type=float, default=8.0)
    load = sub.add_parser("load", help="load processed files into PostgreSQL")
    load.add_argument("--processed", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "generate":
        generate(args.output, args.vehicles, args.seed)
    else:
        if args.command == "run":
            run_pipeline(args.raw, args.processed, args.takt)
        else:
            from assembly_line.db import load_processed
            rows = load_processed(args.processed)
            print(f"Loaded {rows} station events into PostgreSQL")
