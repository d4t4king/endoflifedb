# -*- coding: utf-8 -*-

class EndOfLifeProduct():
    """
        Represents a product record from endoflife.date.  Can be derived from the sqlite database.
    """
    def __init__(self, name: str, **data: dict):
        self.name = name
        self.label = None
        self.category = None
        self.eol_label = None
        self.discontinued = None
        self.eoas = None
        self.eoes = None
        self.html_link = None
        self.icon_link = None
        self.release_policy_link = None
        self.version_command = None

        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)