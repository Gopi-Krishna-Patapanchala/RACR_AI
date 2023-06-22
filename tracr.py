#!/usr/bin/env python3

"""
This script runs the "tracr" CLI, which is powered by the API that lives in 
the "api" folder on this repo.

For a cleaner experience, add this directory to your PATH, which will allow
you to run the CLI from anywhere, and without preceding the command with
the word "python".
"""

import api.network
import api.experiments
import api.exceptions

import argparse


def status(args):
    if args.d:
        print(f"Status for host: {args.d}")
    elif args.e:
        print(f"Status for name: {args.e}")
    else:
        print("Running status")


def run(args):
    if args.e:
        print(f"Running with name: {args.e}")
    else:
        print("Running")


def setup(args):
    if args.d:
        print(f"Setup for host: {args.d}")
    elif args.e:
        print(f"Setup for name: {args.e}")
    else:
        print("Running setup")


def edit(args):
    if args.p:
        print(f"Edit preference: {args.p}")
    elif args.e:
        print(f"Edit for name: {args.e}")
    elif args.d:
        print(f"Edit for host: {args.d}")
    else:
        print("Running edit")


def ls(args):
    if args.d:
        print("Running ls with option -d")
    elif args.e:
        print("Running ls with option -e")
    else:
        print("Running ls")


def main():
    parser = argparse.ArgumentParser(description="My CLI tool")
    subparsers = parser.add_subparsers()

    # Parser for 'status'
    parser_status = subparsers.add_parser("status")
    parser_status.add_argument("-d")
    parser_status.add_argument("-e")
    parser_status.set_defaults(func=status)

    # Parser for 'run'
    parser_run = subparsers.add_parser("run")
    parser_run.add_argument("-e")
    parser_run.set_defaults(func=run)

    # Parser for 'setup'
    parser_setup = subparsers.add_parser("setup")
    parser_setup.add_argument("-d")
    parser_setup.add_argument("-e")
    parser_setup.set_defaults(func=setup)

    # Parser for 'edit'
    parser_edit = subparsers.add_parser("edit")
    parser_edit.add_argument("-p")
    parser_edit.add_argument("-e")
    parser_edit.add_argument("-d")
    parser_edit.set_defaults(func=edit)

    # Parser for 'ls'
    parser_ls = subparsers.add_parser("ls")
    parser_ls.add_argument("-d", action="store_true")
    parser_ls.add_argument("-e", action="store_true")
    parser_ls.set_defaults(func=ls)

    args = parser.parse_args()
    if "func" in args:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
