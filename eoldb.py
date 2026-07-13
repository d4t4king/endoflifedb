#!/usr/bin/env python3

import os
import csv
import copy
import json
import uuid
import pprint
import sqlite3
import argparse
import requests
from typing import Any
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
    """
    Parse and format the command line arguments.
    """
    parser_obj = argparse.ArgumentParser(
        description="Download product date from endoflife.date and convert it into a different format."
    )
    verbose_quiet_debug = parser_obj.add_mutually_exclusive_group()
    verbose_quiet_debug.add_argument('-v', '--verbose', dest='verbose', action='store_true', help="Adds output for more detail.")
    verbose_quiet_debug.add_argument('-q', '--quiet', dest='quiet', action='store_true', help="Suppress all output except warnings and errors.")
    verbose_quiet_debug.add_argument('-D', '--debug', dest='debug', action='store_true', help="Output for debugging.")
    parser_obj.add_argument('--__API_URL', dest="api_url", help=argparse.SUPPRESS)
    parser_obj.add_argument('--csv', action='store_true', help="Enables output to CSV.  This may occlude some of the raw data from endoflife.date.")
    parser_obj.add_argument('-o', '--output-file', dest='output_file', help="The path to the output file.  This may be a path to the sqlite database, if using sqlite.  Or it may be a CSV file, if writing to CSV.")
    parser_obj.add_argument('-t', '--timeout-seconds', default=DEFAULT_TIMEOUT_SECONDS, type=int, help="The number of seconds to wait for a response from the API_URL before quitting.")
    parser_obj.add_argument('-d', '--database-path', default='eol.date.db', help="The path to the sqlite database file.  Will be created if it doesn't exist.")
    parser_obj.add_argument('--show-json', action='store_true', help='Dumps the raw JSON from the API and exits.')
    return parser_obj.parse_args()

def _verbose_pretty_print(enabled: bool, data_object: object, indent: int =4) -> None:
    """
    Optionally prints based on verbosity.  If 'verbose' is enabled, "pretty print" the supplied data object.
    """
    __pretty_printer = pprint.PrettyPrinter(indent=indent)
    if enabled:
        __pretty_printer.pprint(data_object)

def _verbose_print(enabled: bool, message: str, end: str | None ="\n") -> None:
    """
    Optionally prints based on verbosity.
    """
    if enabled:
        print(message, end=end)

def _debug_print(enabled: bool, message: str) -> None:
    """
    Print only if debug is enabled from the command line.
    """
    if enabled:
        print(f"DEBUG: {message}")

def resolve_output_file_path(provided_output_file: str | None) -> Path:
    if provided_output_file:
        return Path(provided_output_file)

    completed_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    generated_filename = (
        f"{DEFAULT_FILE_BASENAME}_{completed_timestamp}{DEFAULT_FILE_EXTENSION}"
    )
    return Path(generated_filename)

def _download_products(timeout_seconds: int, verbose: bool =False, debug: bool =False):
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
    _debug_print(debug, f"json_response_dict is of type {str(type(json_response_dict))}")
    print(f"""
API response schema version: {json_response_dict['schema_version']}
Last Generated at: {json_response_dict['generated_at']}
Total elements in response: {json_response_dict['total']}""")
    print("Number of elements in result: ", end="")
    if json_response_dict['total'] == len(json_response_dict['result']):
        cprint(len(json_response_dict['result']), "green")
    else:
        cprint(len(json_response_dict['result']), "yellow")
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
    for table in sqlite_tables_sql:
        sqlite_reader_writer.create_table(table, sqlite_tables_sql[table], verbose)

def save_product_data(database_file_path: Path, product_data: dict, verbose: bool) -> None:
    sqlite_reader_writer = SQLiteReaderWriter.SQLiteReaderWriter(database_file_path, verbose)
    sqlite_reader_writer.insert_product(product_data, verbose)

def flatten_release(release_data: dict, verbose: bool =False) -> dict:
    flat_release = {}
    for key in release_data:
        if key == "latest":
            if isinstance(release_data[key], dict):
                if "date" in release_data[key]:
                    flat_release['release_latest_date'] = release_data[key]['date']
                else:
                    flat_release['releae_latest_date'] = None
                flat_release['release_latest_link'] = release_data[key]['link']
                flat_release['release_latest_name'] = release_data[key]['name']
            else:
                _verbose_print(verbose, f"Expected dict() for 'latest', got {type(release_data[key])}")
        else:
            new_key_name = f"release_{key}"
            flat_release[new_key_name] = release_data[key]
    #_verbose_pretty_print(verbose, flat_release)
    return flat_release

def format_csv_row_as_dict(product_data: dict[str, Any], verbose: bool =False) -> dict:
    csv_row = {}
    if 'releases' in product_data:
        _verbose_print(verbose, f"Product releases is of type {str(type(product_data['releases']))}")
        _verbose_print(verbose, f"There are {len(product_data['releases'])} releases of this product.")
    else:
        _verbose_print(verbose, f"No releases with this product.")
    for key, value in product_data.items():
        if "identifiers" in key or "releases" in key:
            continue
        if isinstance(value, list):
            _verbose_print(verbose, f"We should only see 'list' here: {type(value)}")
            try:
                product_data[key] = "|".join(value)
            except TypeError as error:
                if "expected str instance, dict found" in str(error):
                    _verbose_pretty_print(True, value)
                else:
                    raise error

    for key in product_data:
        if 'identifiers' in key:
            # skip for now
            _verbose_print(verbose, f"Skipping 'identifiers' key.")
            continue
        # elif key == 'aliases':
        #     aliases = "|".join(product_data[key])
        #     _verbose_print(verbose, f"Got {len(product_data[key])} aliases for product {product_data['name']}: {aliases}")
        #     product_data['aliases'] = aliases
        # elif key == 'tags':
        #     tags = "|".join(product_data[key])
        #     _verbose_print(verbose, f"Got {len(product_data['tags'])} tags for product {product_data['name']}: {tags}")
        #     product_data['tags'] = tags
        elif key == 'versionCommand':
            if product_data[key] is not None:
                csv_row['versionCommand'] = product_data[key].replace('\n', "|")
            else:
                _verbose_print(verbose, "TThe versionCommand value was empty.")
        elif key == 'labels':
            csv_row['labels_discontinued'] = product_data[key]['discontinued']
            csv_row['labels_eoas'] = product_data[key]['eoas']
            csv_row['labels_eoes'] = product_data[key]['eoes']
            csv_row['labels_eol'] = product_data[key]['eol']
        elif key == 'links':
            csv_row['links_html'] = product_data[key]['html']
            csv_row['links_icon'] = product_data[key]['icon']
            csv_row['links_releasePolicy'] = product_data[key]['releasePolicy']
        elif key == 'releases':
            _releases = []
            for release in product_data[key]:
                _releases.append(flatten_release(release))
            _verbose_pretty_print(verbose, _releases)
            csv_row['releases'] = _releases
        else:
            csv_row[key] = product_data[key]
    return csv_row

def format_product_rows(product_data: dict[str, Any], verbose: bool =False) -> list:
    rows = []
    _product_data_xform = format_csv_row_as_dict(product_data)
    if 'releases' in _product_data_xform:
        __releases = copy.deepcopy(_product_data_xform['releases'])
        del _product_data_xform['releases']
        for release in __releases:
            new_product_row = _product_data_xform | release
            rows.append(new_product_row)
    else:
        _verbose_print(verbose, f"No releases in product ({product_data.get('name')})")
        rows.append(product_data)
    return rows

def main() -> int:
    # I guess python "sees" that I am conditionally assigning a value to API_URL and de-scopes it to a local variable.
    global API_URL

    arguments = _parse_arguments()

    if arguments.debug:
        arguments.verbose = True
        _debug_print(arguments.debug, f"Debug output is enabled.")

    if arguments.verbose:
        _verbose_print(arguments.verbose, f"Verbose output is enabled.")

    if arguments.api_url:
        API_URL = arguments.api_url

    products = _download_products(arguments.timeout_seconds, arguments.verbose, arguments.debug)

    if arguments.show_json:
        print("Printing the raw JSON from the API.")
        json_result = _download_products(arguments.timeout_seconds, arguments.verbose)
        _verbose_pretty_print(True, json_result)
    elif arguments.csv:
        print("Preparing end of life data for CSV output.")
        csv_output_rows = []
        output_file_path = resolve_output_file_path(arguments.output_file)
        for product in products:
            _debug_print(arguments.debug, f"Product is of type {str(type(product))}")
            rows = format_product_rows(product, arguments.verbose)
            csv_output_rows.extend(rows)
            _verbose_pretty_print(arguments.verbose, csv_output_rows)
            # break
        
        csv_field_names = ['name', 'category', 'label', 'labels_discontinued', 'labels_eoas', 'labels_eoes', 'labels_eol', 'aliases', 'tags', \
                           'versionCommand', 'links_html', 'links_icon', 'links_releasePolicy', 'release_name', 'release_releaseDate', \
                            'release_label', 'release_codename', 'release_eolFrom', 'release_isEol', 'release_isLts', 'release_isMaintained', \
                            'release_latest_date', 'release_latest_link', 'release_latest_name', 'release_ltsFrom', 'release_isEoas', \
                            'release_eoasFrom', 'release_isEoes', 'release_eoesFrom', 'release_isDiscontinued', 'release_discontinuedFrom', \
                            'release_custom']
        print(f"Got a total of {len(csv_output_rows)} product + release rows.")
        print(f"Writing CSV data to output file ({output_file_path})")
        with open(output_file_path, 'w') as out_file:
            writer = csv.DictWriter(out_file, fieldnames=csv_field_names)
            writer.writeheader()
            writer.writerows(csv_output_rows)
    else:
        # defaults to sqlite storage
        database_file_path = Path(arguments.database_path)
        table_setup(database_file_path, arguments.verbose)
        for product in products:
            #pretty_printer.pprint(product)
            save_product_data(database_file_path, product, arguments.verbose)
    return 0

if __name__=='__main__':
    raise SystemExit(main())