# -*- coding: utf-8 -*-

import uuid
import pprint
import sqlite3
from typing import Any, Literal
from pathlib import Path
from termcolor import cprint
from PIL import ImageColor

import EndofLifeProduct

sqlite3.register_converter("BLOB", lambda b: uuid.UUID(bytes=b))

class SQLiteReaderWriter():

    def __init__(self, database_path: str | Path, verbose: bool):
        """
        Instantiates the SqliteReaderWriter object.  Takes in the path to the sqlite database file and optionally a boolean indicating whether verbose output is enabled.
        Creates the connection and cursor for the sqlite database as object elements.  Minimal object properties will also be populated. 
        TODO: Add **kwargs?
        """
        if 'str' in str(type(database_path)):
            database_path = Path(database_path)
        self.database_path = database_path
        self._verbose_print(verbose, f"Connecting to the database at path {self.database_path} ... ", 'no_color')
        self._sqlite_connection = sqlite3.connect(self.database_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._sqlite_connection.execute("PRAGMA foreign_keys = ON;")
        self._sqlite_cursor = self._sqlite_connection.cursor()
        self._verbose_print(verbose, f"Got cursor object: {self._sqlite_cursor}", 'no_color')

    def _verbose_print(self, enabled: bool, message: str, color: str) -> None:
        """
        Optionally prints based on verbose level (on|off).
        """
        if enabled:
                cprint(f"INFO :: {message}", color) # pyright: ignore[reportArgumentType]

    def __dict_stringify(self, dictionary: dict) -> str:
        """
        Turns a dictionary object into a string (for printing)
        """
        return ",".join(f"{key}={value}" for key, value in dictionary.items())

    def create_table(self, table_name: str, sql: str, verbose: bool) -> bool:
        """
        Sets up all the tables in the sqlite database.
        """
        self._verbose_print(verbose, f"Creating table {table_name} ... ", 'no_color')
        # create the table
        self._sqlite_cursor.execute(sql)

        # It looks like the index shares the same name with the table it's indexing.
        # I'm not even totally sure that an index is or should be directly callable anyway.
        if 'idx_' in table_name or 'CREATE INDEX' in sql:
            self._verbose_print(verbose, f"NOT querying index {table_name}", 'no_color')
            return True
        else:
            # fetching data now automatically returns a UUID object
            self._verbose_print(verbose, f"Testing UUID generation ... ", 'no_color')
            self._sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            row = self._sqlite_cursor.fetchone()
            self._verbose_print(verbose, f"row object: {row}", 'no_color')
            if row:
                return True
            else:
                return False
        
    def get_product(self, product_name: str, verbose: bool =False):
        """
        Looks up a product by name.
        TODO: Figure out how to match any *unique* product attribute.
        """
        self._sqlite_cursor.execute("SELECT id FROM products WHERE name LIKE ?", (product_name,))
        result_id = self._sqlite_cursor.fetchone()
        return result_id

    def compare_product_records(self, record_object_1, record_object_2, verbose: bool =False) -> bool:
        return True
    
    def update_product(self, product_name: str, verbose: bool=False) -> None:
        pass

    def insert_product(self, data: dict[Any, Any], verbose: bool) -> None:
        # connection/cursor should already be setup in the class.
        self._verbose_print(verbose, f"data['name']: {data['name']}", 'no_color')
        product_id = self.get_product(data['name'])
        if product_id is not None:
            print(f"Found a record for product {data['name']} with product id {product_id}")
            return None
        else:
            try:
                # 1. Generate IDs
                self._verbose_print(verbose, f"Generating UUID ... ", 'no_color')
                product_uuid_str = str(uuid.uuid4())
                self._verbose_print(verbose, f"got UUID: {product_uuid_str}", 'no_color')

                # 2. Extract and flatten cor product data
                self._verbose_print(verbose, f"Flattening labels ... ", 'no_color')
                labels = data.get('labels', {})
                self._verbose_print(verbose, f"Flattning links ... ", 'no_color')
                links = data.get('links', {})

                self._verbose_print(verbose, f"Inserting row into products table ... ", 'no_color')
                self._sqlite_cursor.execute("""
                    INSERT INTO products (
                        id, name, label, category, version_command, 
                        eol_label, discontinued, eoas, eoes, 
                        html_link, icon_link, release_policy_link
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    product_uuid_str, data.get('name'), data.get('label'), data.get('category'), data.get('version_command'),
                    labels.get('eol'), labels.get('discontinued'), labels.get('eoas'), labels.get('eoes'), 
                    links.get('html'), links.get('icon'), links.get('releasePolicy')
                ))

                # 3. Insert aliases
                self._verbose_print(verbose, f"Inserting aliases ... ", 'no_color')
                for alias in data.get('aliases', []):
                    self._sqlite_cursor.execute(
                        "INSERT INTO product_aliases (id, product_id, alias) VALUES (?, ?, ?)",
                        (str(uuid.uuid4()), product_uuid_str, alias)
                    )
            
                self._verbose_print(verbose, f"Inserting tags ... ", 'no_color')
                # 4. Insert tags
                for tag in data.get('tags', []):
                    self._sqlite_cursor.execute(
                        "INSERT INTO product_tags (id, product_id, tag) VALUES (?, ?, ?)",
                        (str(uuid.uuid4()), product_uuid_str, tag)
                    )
                
                self._verbose_print(verbose, f"Inserting identifiers ... ", 'no_color')
                #5. Insert identifiers
                for identifier in data.get('identifiers', []):
                    self._sqlite_cursor.execute(
                        "INSERT INTO product_identifiers (id, product_id, type, value) VALUES (?, ?, ?, ?)",
                        (str(uuid.uuid4()), product_uuid_str, identifier.get('type'), identifier.get('id'))
                    )
                
                # 6. Insert releases
                self._verbose_print(verbose, f"Inserting releases ... ", 'no_color')
                for release in data.get('releases', []):
                    latest = release.get('latest', {}) or {}
                    self._verbose_print(verbose, f"INFO :: codename is of type {str(type(release.get('codename')))}", "yellow")
                    self._verbose_print(verbose, f"INFO :: custom is of type {str(type(release.get('custom')))}", "yellow")
                    if 'dict' in str(type(release.get('custom'))):
                        self._verbose_print(verbose, f"release attribute 'custom' is of type {str(type(release.get('custom')))}.", 'no_color')
                        if len(release.get('custom').keys()) == 0:
                            self._verbose_print(verbose, f"release attribute 'custom' has {len(release.get('custom').keys())} keys.  None-ifying.", 'no_color')
                            release['custom'] = None
                        else:
                            print(f"release attribute 'custom' has {len(release.get('custom').keys())} keys.")
                            release['custom'] = self.__dict_stringify(release.get('custom'))
                    # pp = pprint.PrettyPrinter(indent=4)
                    # pp.pprint(release)
                    self._sqlite_cursor.execute("""
                        INSERT INTO product_releases (
                        id, product_id, name, label, codename, custom, 
                        release_date, eol_from, lts_from, is_eol, is_lts, is_maintained,
                        latest_version_name, latest_version_date, latest_version_link
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(uuid.uuid4()), product_uuid_str, release.get('name'), release.get('label'), release.get('codename'), release.get('custom'),
                        release.get('releaseDate'), release.get('eolFrom'), release.get('ltsFrom'),
                        1 if release.get('isEol') else 0,
                        1 if release.get('isLts') else 0,
                        1 if release.get('isMaintained') else 0,
                        latest.get('name'), latest.get('date'), latest.get('link')
                    ))

                self._sqlite_connection.commit()
                print("Product safely ingested into SQLite database.")
            except sqlite3.IntegrityError as error:
                self._sqlite_connection.rollback()
                self._verbose_print(verbose, f"{error}", 'no_color')
            except sqlite3.Error as error:
                self._sqlite_connection.rollback()
                print(f"ERROR :: Database error: {error}")
                print(f"ERROR ::   product_name: {data.get('name')}")
                print(f"ERROR ::   custom: {data.get('custom', {})}")
                raise error
            finally:
                self._sqlite_connection.close()