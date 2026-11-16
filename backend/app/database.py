from pymongo import MongoClient

from .backoffice import Backoffice
from .config import MONGODB_DATABASE, MONGODB_URI


class MongoStore:
    """MongoDB access: the Carry Forward, the daily net positions and prices."""

    def __init__(self, database=None):
        self.client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2500)
        self.db = self.client[database or MONGODB_DATABASE]
        self.backoffice = Backoffice(self.db)

    def ping(self):
        self.client.admin.command("ping")

    def indexes(self):
        self.backoffice.carry_forward.ensure_indexes()
        self.backoffice.closing_rates.ensure_indexes()
        self.backoffice.bhavcopy.ensure_indexes()

    def close(self):
        self.client.close()
