#!/usr/bin/env python3
"""Teardown GCP infrastructure for RAG-as-a-Service.

Deletes:
- Cloud Run service
- Cloud Storage bucket (with all documents)
- Cloud SQL instance
- Service Account

Usage:
    python deployment/teardown.py
"""

import os
import sys
import subprocess
from pathlib import Path


def print_info(msg: str):
    """Print info message."""
    print(f"[INFO] {msg}")


def print_success(msg: str):
    """Print success message."""
    print(f"[SUCCESS] {msg}")


def print_error(msg: str):
    """Print error message."""
    print(f"[ERROR] {msg}", file=sys.stderr)


def print_warn(msg: str):
    """Print warning message."""
    print(f"[WARN] {msg}")


def run_command(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    """Run shell command and return result."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    
    if check and result.returncode != 0:
        print_error(f"Command failed: {' '.join(cmd)}")
        print_error(f"Error: {result.stderr}")
    
    return result


def load_config() -> dict:
    """Load deployment configuration."""
    config = {}
    deploy_dir = Path(__file__).parent
    
    # Try .env.deploy first
    env_deploy_path = deploy_dir / '.env.deploy'
    if env_deploy_path.exists():
        with open(env_deploy_path) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    config[key] = value.strip('"')
    
    # Try .env
    env_path = deploy_dir.parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    config[key] = value.strip('"')
    
    # Set defaults
    config.setdefault('GCS_BUCKET', f"{config.get('GCP_PROJECT_ID', 'unknown')}-rag-documents")
    config.setdefault('CLOUD_SQL_INSTANCE', 'rag-postgres')
    config.setdefault('SERVICE_ACCOUNT_NAME', 'rag-service')
    config.setdefault('CLOUD_RUN_SERVICE', 'rag-api')
    
    return config


def confirm_deletion() -> bool:
    """Ask user to confirm deletion."""
    print_warn("")
    print_warn("=" * 60)
    print_warn("WARNING: This will DELETE ALL infrastructure and data!")
    print_warn("=" * 60)
    print_warn("")
    print_warn("This action will:")
    print_warn("  - Delete Cloud Run service")
    print_warn("  - Delete ALL documents in GCS bucket")
    print_warn("  - Delete Cloud SQL instance and ALL data")
    print_warn("  - Delete Service Account")
    print_warn("  - Delete local .env and credentials.txt files")
    print_warn("")
    print_warn("This action CANNOT be undone!")
    print_warn("")
    
    response = input("Type 'DELETE-ALL' to confirm: ")
    return response == 'DELETE-ALL'


def delete_cloud_run(service_name: str, region: str, project_id: str):
    """Delete Cloud Run service."""
    print_info(f"Deleting Cloud Run service: {service_name}...")
    
    result = run_command([
        'gcloud', 'run', 'services', 'delete', service_name,
        '--region', region,
        '--project', project_id,
        '--quiet'
    ])
    
    if result.returncode == 0:
        print_success(f"Cloud Run service {service_name} deleted")
    else:
        print_warn(f"Cloud Run service {service_name} not found or already deleted")


def delete_gcs_bucket(bucket_name: str, project_id: str):
    """Delete GCS bucket."""
    print_info(f"Deleting GCS bucket: {bucket_name}...")
    
    # Delete all objects first
    print_info("  Deleting all objects...")
    run_command([
        'gcloud', 'storage', 'rm', '-r', f'gs://{bucket_name}',
        '--project', project_id
    ])
    
    if result.returncode == 0:
        print_success(f"GCS bucket {bucket_name} deleted")
    else:
        print_warn(f"GCS bucket {bucket_name} not found or already deleted")


def delete_cloud_sql(instance_name: str, project_id: str):
    """Delete Cloud SQL instance."""
    print_info(f"Deleting Cloud SQL instance: {instance_name}...")
    
    result = run_command([
        'gcloud', 'sql', 'instances', 'delete', instance_name,
        '--project', project_id,
        '--quiet'
    ])
    
    if result.returncode == 0:
        print_success(f"Cloud SQL instance {instance_name} deleted")
    else:
        print_warn(f"Cloud SQL instance {instance_name} not found or already deleted")


def delete_service_account(sa_name: str, project_id: str):
    """Delete service account."""
    print_info(f"Deleting service account: {sa_name}...")
    
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    
    result = run_command([
        'gcloud', 'iam', 'service-accounts', 'delete', sa_email,
        '--project', project_id,
        '--quiet'
    ])
    
    if result.returncode == 0:
        print_success(f"Service account {sa_email} deleted")
    else:
        print_warn(f"Service account {sa_email} not found or already deleted")


def delete_local_files():
    """Delete local configuration files."""
    print_info("Deleting local configuration files...")
    
    deploy_dir = Path(__file__).parent
    files_to_delete = [
        deploy_dir.parent / '.env',
        deploy_dir / 'credentials.txt'
    ]
    
    for file_path in files_to_delete:
        if file_path.exists():
            file_path.unlink()
            print_success(f"  Deleted {file_path.name}")


def main():
    """Main teardown function."""
    print_info("RAG-as-a-Service Infrastructure Teardown")
    print_info("=" * 50)
    
    # Load config
    config = load_config()
    if not config.get('GCP_PROJECT_ID'):
        print_error("Cannot load configuration - no GCP_PROJECT_ID found")
        print_info("Make sure .env.deploy or .env exists")
        sys.exit(1)
    
    print_info(f"Project: {config['GCP_PROJECT_ID']}")
    print_info(f"Region: {config.get('GCP_REGION', 'unknown')}")
    
    # Confirm deletion
    if not confirm_deletion():
        print_info("Teardown cancelled")
        sys.exit(0)
    
    print_info("")
    print_info("Starting teardown...")
    
    # Delete in reverse order
    delete_cloud_run(
        config['CLOUD_RUN_SERVICE'],
        config.get('GCP_REGION', 'us-central1'),
        config['GCP_PROJECT_ID']
    )
    
    delete_gcs_bucket(
        config['GCS_BUCKET'],
        config['GCP_PROJECT_ID']
    )
    
    delete_cloud_sql(
        config['CLOUD_SQL_INSTANCE'],
        config['GCP_PROJECT_ID']
    )
    
    delete_service_account(
        config['SERVICE_ACCOUNT_NAME'],
        config['GCP_PROJECT_ID']
    )
    
    delete_local_files()
    
    print_info("")
    print_success("Teardown complete!")
    print_info("")
    print_info("All infrastructure has been deleted.")
    print_info("")


if __name__ == '__main__':
    main()
