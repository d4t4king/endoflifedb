
import uuid
import sqlite3
from typing import Any
from pathlib import Path
from termcolor import cprint

sqlite3.register_converter("BLOB", lambda b: uuid.UUID(bytes=b))

class SQLiteReaderWriter():

    def __init__(self, database_path: str | Path, verbose: bool):
        if 'str' in str(type(database_path)):
            database_path = Path(database_path)
        self.database_path = database_path
        self._verbose_print(verbose, f"Connecting to the database at path {self.database_path} ... ")
        self._sqlite_connection = sqlite3.connect(self.database_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self._sqlite_connection.execute("PRAGMA foreign_keys = ON;")
        self._sqlite_cursor = self._sqlite_connection.cursor()
        self._verbose_print(verbose, f"Got cursor object: {self._sqlite_cursor}")

    def _verbose_print(self, enabled: bool, message: str) -> None:
        if enabled:
            print(f"INFO :: {message}")

    def create_table(self, table_name: str, sql: str, verbose: bool) -> bool:
        self._verbose_print(verbose, f"Creating table {table_name} ... ")
        # create the table
        self._sqlite_cursor.execute(sql)

        # It looks like the index shares the same name with the table it's indexing.
        # I'm not even totally sure that an index is or should be directly callable anyway.
        if 'idx_' in table_name or 'CREATE INDEX' in sql:
            print(f"NOT querying index {table_name}")
            return True
        else:
            # fetching data now automatically returns a UUID object
            self._verbose_print(verbose, f"Testing UUID generation ... ")
            self._sqlite_cursor.execute(f"SELECT * FROM {table_name}")
            row = self._sqlite_cursor.fetchone()
            self._verbose_print(verbose, f"row object: {row}")
            if row:
                return True
            else:
                return False
        
    def insert_product(self, data: dict[Any, Any], verbose: bool) -> None:
        # connection/cursor should already be setup in the class.
        try:
            # 1. Generate IDs
            self._verbose_print(verbose, f"Generating UUID ... ")
            product_uuid_str = str(uuid.uuid4())
            self._verbose_print(verbose, f"got UUID: {product_uuid_str}")

            # 2. Extract and flatten cor product data
            self._verbose_print(verbose, f"Flattening labels ... ")
            labels = data.get('labels', {})
            self._verbose_print(verbose, f"Flattning links ... ")
            links = data.get('links', {})

            self._verbose_print(verbose, f"Inserting row into products table ... ")
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
            self._verbose_print(verbose, f"Inserting aliases ... ")
            for alias in data.get('aliases', []):
                self._sqlite_cursor.execute(
                    "INSERT INTO product_aliases (id, product_id, alias) VALUES (?, ?, ?)",
                    (str(uuid.uuid4()), product_uuid_str, alias)
                )
        
            self._verbose_print(verbose, f"Inserting tags ... ")
            # 4. Insert tags
            for tag in data.get('tags', []):
                self._sqlite_cursor.execute(
                    "INSERT INTO product_tags (id, product_id, tag) VALUES (?, ?, ?)",
                    (str(uuid.uuid4()), product_uuid_str, tag)
                )
            
            self._verbose_print(verbose, f"Inserting identifiers ... ")
            #5. Insert identifiers
            for identifier in data.get('identifiers', []):
                self._sqlite_cursor.execute(
                    "INSERT INTO product_identifiers (id, product_id, type, value) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), product_uuid_str, identifier.get('type'), identifier.get('id'))
                )
            
            # 6. Insert releases
            self._verbose_print(verbose, f"Inserting releases ... ")
            for release in data.get('releases', []):
                latest = release.get('latest', {}) or {}
                cprint(f"INFO :: codename is of type {str(type(release.get('codename')))}", "yellow")
                cprint(f"INFO :: custom is of type {str(type(release.get('custom')))}", "yellow")
                if 'dict' in str(type(release.custom)):
                    if len(release.custom.keys()) == 0:
                        release.custom = None
                    else:
                        print(f"Got {len(release.get('custom').keys())}")
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
        except sqlite3.Error as error:
            self._sqlite_connection.rollback()
            print(f"ERROR :: Database error: {error}")
            print(f"ERROR ::   product_name: {data.get('name')}")
            print(f"ERROR ::   custom: {data.get('custom', {})}")
            raise error
        finally:
            self._sqlite_connection.close()