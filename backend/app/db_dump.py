"""Export / import the whole MongoDB database as one compressed file.

    # export every collection (data + indexes) to one .bson.gz file
    python -m app.db_dump export
    python -m app.db_dump export --out D:\\backup\\pnl.bson.gz

    # load that file into the database (replaces each collection it contains)
    python -m app.db_dump import data\\db_dumps\\trade_ingestion_20261116_1530.bson.gz
    python -m app.db_dump import latest      # newest file in data\\db_dumps\\

Uses MONGODB_URI / MONGODB_DATABASE from .env (override with --uri / --db).

File format: gzip of a stream of BSON documents, so every type (ObjectId, dates,
Decimal128, ...) round-trips exactly. The first record of each collection is
{"_meta": {"collection", "indexes"}}; every data record is {"_c": name, "_d": doc}.
The file holds client data: keep it out of git (backend/data/ is git-ignored).
"""
from __future__ import annotations

import argparse
import gzip
from datetime import datetime
from pathlib import Path

import bson
from pymongo import MongoClient

from .config import MONGODB_DATABASE, MONGODB_URI

BATCH = 1000
INDEX_OPTIONS = ("unique", "sparse", "partialFilterExpression", "expireAfterSeconds", "collation")
DEFAULT_DIR = Path(__file__).resolve().parents[1] / "data" / "db_dumps"


def _index_specs(collection):
    specs = []
    for name, info in collection.index_information().items():
        if name == "_id_":
            continue
        spec = {"name": name, "key": [[field, direction] for field, direction in info["key"]]}
        spec.update({opt: info[opt] for opt in INDEX_OPTIONS if opt in info})
        specs.append(spec)
    return specs


def export_db(db, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {}
    with gzip.open(out_path, "wb", compresslevel=6) as fh:
        for name in sorted(db.list_collection_names()):
            if name.startswith("system."):
                continue
            collection = db[name]
            fh.write(bson.encode({"_meta": {"collection": name, "indexes": _index_specs(collection)}}))
            n = 0
            for doc in collection.find({}, batch_size=BATCH):
                fh.write(bson.encode({"_c": name, "_d": doc}))
                n += 1
            counts[name] = n
    return counts


def import_db(db, in_path, drop=True):
    counts, indexes, batch, current = {}, {}, [], None

    def flush():
        if batch:
            db[current].insert_many(batch, ordered=False)
            counts[current] = counts.get(current, 0) + len(batch)
            batch.clear()

    with gzip.open(in_path, "rb") as fh:
        for record in bson.decode_file_iter(fh):
            if "_meta" in record:
                flush()
                current = record["_meta"]["collection"]
                indexes[current] = record["_meta"]["indexes"]
                counts.setdefault(current, 0)
                if drop:
                    db[current].drop()
                continue
            if record["_c"] != current:
                flush()
                current = record["_c"]
            batch.append(record["_d"])
            if len(batch) >= BATCH:
                flush()
        flush()

    for name, specs in indexes.items():
        for spec in specs:
            options = {k: v for k, v in spec.items() if k != "key"}
            db[name].create_index([(field, direction) for field, direction in spec["key"]], **options)
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export / import the MongoDB database as one file.")
    parser.add_argument("--uri", default=MONGODB_URI)
    parser.add_argument("--db", default=MONGODB_DATABASE)
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="write every collection to one .bson.gz file")
    exp.add_argument("--out", help="output file (default: data/db_dumps/<db>_<timestamp>.bson.gz)")
    imp = sub.add_parser("import", help="load a .bson.gz file into the database")
    imp.add_argument("file", help='path to the .bson.gz file, or "latest" for the newest file in data/db_dumps/')
    imp.add_argument("--keep", action="store_true", help="add to existing collections instead of replacing them")
    args = parser.parse_args(argv)

    if args.command == "import":
        if args.file.lower() == "latest":
            dumps = sorted(DEFAULT_DIR.glob("*.bson.gz"), key=lambda p: p.stat().st_mtime)
            if not dumps:
                raise SystemExit(f"No backup files in {DEFAULT_DIR}. Run: python -m app.db_dump export")
            args.file = str(dumps[-1])
        elif not Path(args.file).is_file():
            found = sorted(DEFAULT_DIR.glob("*.bson.gz"))
            hint = "\n".join(f"  {p}" for p in found) or "  (none yet; run: python -m app.db_dump export)"
            raise SystemExit(f"File not found: {args.file}\nBackups in {DEFAULT_DIR}:\n{hint}")
        print(f"Importing {args.file}")

    client = MongoClient(args.uri, serverSelectionTimeoutMS=10000)
    db = client[args.db]
    try:
        client.admin.command("ping")
        if args.command == "export":
            out = args.out or DEFAULT_DIR / f"{args.db}_{datetime.now():%Y%m%d_%H%M}.bson.gz"
            counts = export_db(db, out)
            size = Path(out).stat().st_size / 1024 / 1024
            print(f"Exported {sum(counts.values()):,} documents from {len(counts)} collections of '{args.db}' to {out} ({size:.1f} MB)")
        else:
            counts = import_db(db, args.file, drop=not args.keep)
            print(f"Imported {sum(counts.values()):,} documents into {len(counts)} collections of '{args.db}'")
        for name, n in counts.items():
            print(f"  {name:24s} {n:>9,}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
