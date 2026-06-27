"""CLI entry point — process one or more invoice documents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-Modal Document Intelligence Agent — Invoice & Form Processing"
    )
    parser.add_argument("paths", nargs="+", help="PDF or image file(s) to process")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--list", action="store_true", help="List all stored records")
    args = parser.parse_args()

    if args.list:
        from database.storage import list_records
        records = list_records()
        print(json.dumps(records, indent=2, default=str))
        return

    from graph.workflow import process_document

    results = []
    for path in args.paths:
        p = Path(path)
        if not p.exists():
            print(f"[ERROR] File not found: {path}", file=sys.stderr)
            continue

        print(f"\nProcessing: {p.name} ...", file=sys.stderr)
        state = process_document(str(p))

        result = {
            "document_id": state["document_id"],
            "source": path,
            "status": state["final_status"].value if state["final_status"] else "unknown",
            "data": state["extraction"].extracted_data.model_dump() if state["extraction"] else {},
            "notes": state["processing_notes"],
        }
        results.append(result)

        if args.json:
            pass  # printed at end
        else:
            _pretty_print(result)

    if args.json:
        print(json.dumps(results, indent=2, default=str))


def _pretty_print(result: dict) -> None:
    data = result["data"]
    print(f"\n{'='*60}")
    print(f"  Document ID : {result['document_id']}")
    print(f"  Status      : {result['status'].upper()}")
    print(f"  Vendor      : {data.get('vendor_name', 'N/A')}")
    print(f"  Invoice #   : {data.get('invoice_number', 'N/A')}")
    print(f"  Date        : {data.get('invoice_date', 'N/A')}")
    print(f"  Total       : {data.get('currency', '')} {data.get('total_amount', 'N/A')}")
    if data.get("line_items"):
        print(f"  Line Items  : {len(data['line_items'])} item(s)")
    print(f"  Notes       : {'; '.join(result['notes'])}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
