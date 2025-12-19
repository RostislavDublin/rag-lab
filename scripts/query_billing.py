#!/usr/bin/env python3
"""
Query BigQuery billing export using Python API.
Does not depend on gcloud CLI project settings.
Uses user's OAuth token from get_user_token.py.
"""

import sys
import subprocess
import os
from pathlib import Path
from google.cloud import bigquery
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

# Load .env.local for CLIENT_ID and CLIENT_SECRET
project_root = Path(__file__).parent.parent
env_path = project_root / ".env.local"
load_dotenv(env_path)


def get_credentials() -> Credentials:
    """Get OAuth2 credentials with refresh capability."""
    # Get user's OAuth token
    script_path = Path(__file__).parent / "get_user_token.py"
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=True,
        timeout=120
    )
    token = result.stdout.strip()
    
    # Reload env to get refresh_token (saved by get_user_token.py)
    load_dotenv(env_path, override=True)
    refresh_token = os.getenv("REFRESH_TOKEN")
    
    # Create credentials with refresh capability
    return Credentials(
        token=token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("AUDIENCE"),  # CLIENT_ID
        client_secret=os.getenv("CLIENT_SECRET")
    )


def query_billing(sql: str, project_id: str = "myai-475419") -> None:
    """
    Execute a BigQuery query and print results.
    
    Args:
        sql: SQL query to execute
        project_id: GCP project ID (default: myai-475419)
    """
    credentials = get_credentials()
    
    # Create BigQuery client
    client = bigquery.Client(
        credentials=credentials,
        project=project_id
    )
    
    try:
        # Execute query
        query_job = client.query(sql)
        results = query_job.result()
        
        # Print results
        print("\nQuery Results:")
        print("=" * 80)
        
        if results.total_rows == 0:
            print("No data found.")
        else:
            # Print column headers
            headers = [field.name for field in results.schema]
            header_line = " | ".join(f"{h:20}" for h in headers)
            print(header_line)
            print("-" * len(header_line))
            
            # Print rows
            for row in results:
                row_values = [str(row[field.name]) for field in results.schema]
                row_line = " | ".join(f"{v:20}" for v in row_values)
                print(row_line)
        
        print("=" * 80)
        print(f"Total rows: {results.total_rows}")
        print(f"Bytes processed: {query_job.total_bytes_processed:,}")
        print(f"Bytes billed: {query_job.total_bytes_billed:,}")
        
    except Exception as e:
        print(f"Error executing query: {e}", file=sys.stderr)
        sys.exit(1)


def list_tables(project_id: str = "myai-475419", dataset_id: str = "billing_export") -> None:
    """List all tables in billing_export dataset."""
    credentials = get_credentials()
    client = bigquery.Client(credentials=credentials, project=project_id)
    
    try:
        tables = client.list_tables(f"{project_id}.{dataset_id}")
        print(f"\nTables in {project_id}.{dataset_id}:")
        print("=" * 80)
        
        table_list = list(tables)
        if not table_list:
            print("No tables found yet. Billing export data will appear in 24-48 hours.")
        else:
            for table in table_list:
                print(f"  - {table.table_id}")
        
        print("=" * 80)
        
    except Exception as e:
        print(f"Error listing tables: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/query_billing.py --list-tables")
        print('  python scripts/query_billing.py "SELECT ..."')
        print("\nExamples:")
        print('  python scripts/query_billing.py --list-tables')
        print('  python scripts/query_billing.py "SELECT COUNT(*) FROM `myai-475419.billing_export.INFORMATION_SCHEMA.TABLES`"')
        sys.exit(1)
    
    if sys.argv[1] == "--list-tables":
        list_tables()
    else:
        query_billing(sys.argv[1])


if __name__ == "__main__":
    main()
