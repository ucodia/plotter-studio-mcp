"""Pen and paper inventory loading from xlsx or csv files."""

import os
from pathlib import Path
from typing import Dict, List


def _load_spreadsheet(file_path: str) -> List[Dict[str, str]]:
    """Load rows from an xlsx or csv file as a list of dicts."""
    if not file_path or not os.path.exists(file_path):
        return []

    path = Path(file_path)

    if path.suffix in (".xlsx", ".xls"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h).strip().lower() for h in rows[0]]
        return [
            {headers[i]: str(cell) if cell is not None else "" for i, cell in enumerate(row)}
            for row in rows[1:]
        ]

    elif path.suffix == ".csv":
        import csv

        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [
                {k.strip().lower(): v.strip() for k, v in row.items()} for row in reader
            ]

    return []


def _load_inventory(inventory_path: str) -> List[Dict[str, str]]:
    """Load pen inventory from an xlsx or csv file."""
    return _load_spreadsheet(inventory_path)


def _load_paper_inventory(paper_path: str) -> List[Dict[str, str]]:
    """Load paper inventory from an xlsx or csv file."""
    return _load_spreadsheet(paper_path)
