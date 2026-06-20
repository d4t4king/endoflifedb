#!/usr/bin/env python3

import os
import csv
import json
import uuid
import pprint
import sqlite3
import argparse
import requests
from pathlib import Path
from termcolor import cprint
from datetime import datetime
from urllib.error import HTTPError, URLError

import SQLiteReaderWriter

API_URL = "https://endoflife.date/api/v1/products/full"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_FILE_BASENAME = "eol_products"
DEFAULT_FILE_EXTENSION = ".csv"

def _parse_arguments() -> argparse.Namespace:
    parser_obj = argparse.ArgumentParser(
        description="Download product date from endoflife.date and convert it into a different format."
    )
    verbose_quiet_debug = parser_obj.add_mutually_exclusive_group()
    verbose_quiet_debug.add_argument('-v', '--verbose', dest='verbose', action='store_true', help="Adds output for more detail.")
    verbose_quiet_debug.add_argument('-q', '--quiet', dest='quiet', action='store_true', help="Suppress all output except warnings and errors.")
    verbose_quiet_debug.add_argument('-D', '--debug', dest='debug', action='store_true', help="Output for debugging.")
    parser_obj.add_argument('--__API_URL', dest="api_url", help=argparse.SUPPRESS)
    parser_obj.add_argument('-o', '--output-file', dest='output_file', help="The path to the output file.  This may be a path to the sqlite database, if using sqlite.  Or it may be a CSV file, if writing to CSV.")
    parser_obj.add_argument('-t', '--timeout-seconds', default=DEFAULT_TIMEOUT_SECONDS, type=int, help="The number of seconds to wait for a response from the API_URL before quitting.")
    parser_obj.add_argument('-d', '--database-path', default='eol.date.db', help="The path to the sqlite database file.  Will be created if it doesn't exist.")
    return parser_obj.parse_args()

def _verbose_print(enabled: bool, message: str, end: str | None ="\n") -> None:
    if enabled:
        print(message, end=end)

def _debug_print(enabled: bool, message: str) -> None:
    if enabled:
        print(f"DEBUG: {message}")

def _resolve_output_file_path(provided_output_file: str | None) -> Path:
    if provided_output_file:
        return Path(provided_output_file)

    completed_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    generated_filename = (
        f"{DEFAULT_FILE_BASENAME}_{completed_timestamp}{DEFAULT_FILE_EXTENSION}"
    )
    return Path(generated_filename)

def _download_products(timeout_seconds: int, verbose: bool):
    _verbose_print(verbose, f"Downloading data from {API_URL} ... ", "")
    try:
        request = requests.get(url=API_URL, timeout=timeout_seconds)
        request.raise_for_status()
        json_response_dict = request.json()
    except requests.exceptions.HTTPError as http_error:
        print(f"HTTP error occurred: {http_error}")
    except requests.exceptions.ConnectionError as connection_error:
        print(f"Connection error occurred: {connection_error}")
    except requests.exceptions.Timeout as timeout_error:
        print(f"The request timed out after {timeout_seconds} seconds: {timeout_error}")
    except requests.exceptions.JSONDecodeError as json_error:
        print(f"Failed to parse response as JSON: {json_error}")
    except requests.exceptions.RequestException as request_error:
        print(f"A broader request error occurred: {request_error}")
    _verbose_print(verbose, f"done")
    _verbose_print(verbose, f"json_response_dict is of type {str(type(json_response_dict))}")
    print(f"""
API response schema version: {json_response_dict['schema_version']}
Last Generated at: {json_response_dict['generated_at']}
Total elements in response: {json_response_dict['total']}""")
    print("Number of elements in result: ", end="")
    if json_response_dict['total'] == len(json_response_dict['result']):
        cprint(len(json_response_dict['result']), "green")
    else:
        cprint(len(json_response_dict['result']), "yellow")
    print()
    return json_response_dict['result']

def table_setup(database_file_path: str | Path, verbose: bool) -> None:
    sqlite_tables_sql = {
        'products': "CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, label TEXT NOT NULL, category TEXT NOT NULL, version_command TEXT, eol_label TEXT, discontinued TEXT, eoas TEXT, eoes TEXT, html_link TEXT, icon_link TEXT, release_policy_link TEXT);",
        'product_aliases': "CREATE TABLE IF NOT EXISTS product_aliases ( id TEXT PRIMARY KEY, product_id TEXT NOT NULL, alias TEXT NOT NULL, FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE, UNIQUE(product_id, alias));",
        'product_tags': "CREATE TABLE IF NOT EXISTS product_tags ( id TEXT PRIMARY KEY, product_id TEXT NOT NULL, tag TEXT NOT NULL, FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE, UNIQUE(product_id, tag));",
        'product_identifiers': "CREATE TABLE IF NOT EXISTS product_identifiers ( id TEXT PRIMARY KEY, product_id TEXT NOT NULL, type TEXT NOT NULL, value TEXT NOT NULL, FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE);",
        'product_releases': "CREATE TABLE IF NOT EXISTS product_releases ( id TEXT PRIMARY KEY, product_id TEXT NOT NULL, name TEXT NOT NULL, label TEXT NOT NULL, codename TEXT, custom TEXT, release_date TEXT, eol_from TEXT, lts_from TEXT, is_eol INTEGER NOT NULL CHECK (is_eol IN (0,1)), is_lts INTEGER NOT NULL CHECK (is_lts IN (0,1)), is_maintained INTEGER NOT NULL CHECK (is_maintained IN (0,1)), latest_version_name TEXT, latest_version_date TEXT, latest_version_link TEXT, FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE);",
        'idx_product_tags_tag': "CREATE INDEX IF NOT EXISTS idx_product_tags_tag ON product_tags(tag);",
        'idx_product_aliases_alias': "CREATE INDEX IF NOT EXISTS idx_product_aliases_alias ON product_aliases(alias);",
        'idx_identifiers_lookup': "CREATE INDEX IF NOT EXISTS idx_identifiers_lookup ON product_identifiers(type, value);",
        'idx_releases_maintained': "CREATE INDEX IF NOT EXISTS idx_releases_maintained ON product_releases(is_maintained);",
        'idx_releases_lookup': "CREATE INDEX IF NOT EXISTS idx_releases_lookup ON product_releases(product_id, name);"
    }

    sqlite_reader_writer = SQLiteReaderWriter.SQLiteReaderWriter(database_file_path, verbose)
    for table in sqlite_tables_sql.keys():
        sqlite_reader_writer.create_table(table, sqlite_tables_sql[table], verbose)

def save_product_data(database_file_path: Path, product_data: dict, verbose: bool) -> None:
    sqlite_reader_writer = SQLiteReaderWriter.SQLiteReaderWriter(database_file_path, verbose)
    sqlite_reader_writer.insert_product(product_data, verbose)

def main() -> int:
    global API_URL

    pretty_printer = pprint.PrettyPrinter(indent=4)

    arguments = _parse_arguments()

    if arguments.debug:
        arguments.verbose = True

    if arguments.api_url:
        API_URL = arguments.api_url

    database_file_path = Path(arguments.database_path)
    table_setup(database_file_path, arguments.verbose)

    products = _download_products(arguments.timeout_seconds, arguments.verbose)
    for product in products:
        #pretty_printer.pprint(product)
        save_product_data(database_file_path, product, arguments.verbose)

    output_file_path = _resolve_output_file_path(arguments.output_file)                 # <-- This is really for the CSV output, which we aren't implementing yet.

    return 0

if __name__=='__main__':
    raise SystemExit(main())