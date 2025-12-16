#!/usr/bin/env python3
"""Setup GCP infrastructure for RAG-as-a-Service.

Creates:
- Cloud Storage bucket for documents
- Cloud SQL PostgreSQL instance
- Service Account with IAM roles
- Enables required APIs

Usage:
    python deployment/setup_infrastructure.py
"""

import os
import sys
import json
import subprocess
import secrets
import string
from pathlib import Path
from typing import Optional


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


def run_command(cmd: list[str], check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run shell command and return result."""
    result = subprocess.run(
        cmd,
        capture_output=capture_output,
        text=True,
        check=False
    )
    
    if check and result.returncode != 0:
        print_error(f"Command failed: {' '.join(cmd)}")
        print_error(f"Error: {result.stderr}")
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    
    return result


def load_config() -> dict:
    """Load deployment configuration from .env.deploy."""
    config = {}
    deploy_dir = Path(__file__).parent
    env_path = deploy_dir / '.env.deploy'
    
    if not env_path.exists():
        print_error("deployment/.env.deploy not found")
        print_info("Copy .env.deploy.example to .env.deploy and configure it")
        sys.exit(1)
    
    with open(env_path) as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.strip().split('=', 1)
                config[key] = value.strip('"')
    
    # Validate required fields
    required = ['GCP_PROJECT_ID', 'GCP_REGION']
    missing = [k for k in required if not config.get(k)]
    if missing:
        print_error(f"Missing required fields in .env.deploy: {', '.join(missing)}")
        sys.exit(1)
    
    # Set defaults
    config.setdefault('GCS_BUCKET', f"{config['GCP_PROJECT_ID']}-rag-documents")
    config.setdefault('CLOUD_SQL_INSTANCE', 'rag-postgres')
    config.setdefault('SERVICE_ACCOUNT_NAME', 'rag-service')
    config.setdefault('DB_NAME', 'rag_db')
    config.setdefault('DB_USER', 'rag_user')
    
    # Generate DB password if not provided
    if not config.get('DB_PASSWORD'):
        alphabet = string.ascii_letters + string.digits
        config['DB_PASSWORD'] = ''.join(secrets.choice(alphabet) for _ in range(32))
    
    return config


def check_gcloud_auth() -> bool:
    """Check if gcloud is authenticated."""
    result = run_command(['gcloud', 'auth', 'list', '--format=json'], check=False)
    if result.returncode != 0:
        return False
    
    accounts = json.loads(result.stdout)
    active = [acc for acc in accounts if acc.get('status') == 'ACTIVE']
    return len(active) > 0


def enable_apis(project_id: str):
    """Enable required GCP APIs."""
    print_info("Enabling required APIs...")
    
    apis = [
        'run.googleapis.com',
        'cloudbuild.googleapis.com',
        'sqladmin.googleapis.com',
        'storage.googleapis.com',
        'aiplatform.googleapis.com',
        'iam.googleapis.com'
    ]
    
    for api in apis:
        print_info(f"  Enabling {api}...")
        result = run_command(
            ['gcloud', 'services', 'enable', api, '--project', project_id],
            check=False
        )
        if result.returncode == 0:
            print_success(f"  {api} enabled")
        else:
            print_warn(f"  {api} already enabled or failed")


def create_gcs_bucket(bucket_name: str, region: str, project_id: str) -> bool:
    """Create GCS bucket."""
    print_info(f"Creating GCS bucket: {bucket_name}...")
    
    # Check if exists
    result = run_command(
        ['gcloud', 'storage', 'buckets', 'describe', f'gs://{bucket_name}', '--project', project_id],
        check=False
    )
    if result.returncode == 0:
        print_warn(f"Bucket {bucket_name} already exists")
        return True
    
    # Create bucket
    result = run_command(
        ['gcloud', 'storage', 'buckets', 'create', f'gs://{bucket_name}',
         '--location', region,
         '--uniform-bucket-level-access',
         '--project', project_id],
        check=False
    )
    
    if result.returncode == 0:
        print_success(f"Bucket {bucket_name} created")
        return True
    else:
        print_error(f"Failed to create bucket: {result.stderr}")
        return False


def create_cloud_sql_instance(instance_name: str, region: str, project_id: str, 
                               db_name: str, db_user: str, db_password: str) -> Optional[str]:
    """Create Cloud SQL instance."""
    print_info(f"Creating Cloud SQL instance: {instance_name}...")
    
    # Check if exists
    result = run_command(
        ['gcloud', 'sql', 'instances', 'describe', instance_name, '--project', project_id],
        check=False
    )
    if result.returncode == 0:
        print_warn(f"Instance {instance_name} already exists")
        # Get connection name
        instance_info = json.loads(result.stdout)
        connection_name = instance_info['connectionName']
        return connection_name
    
    # Create instance
    print_info("Creating Cloud SQL instance (this takes 5-10 minutes)...")
    result = run_command(
        ['gcloud', 'sql', 'instances', 'create', instance_name,
         '--database-version', 'POSTGRES_15',
         '--tier', 'db-f1-micro',
         '--region', region,
         '--storage-type', 'HDD',
         '--storage-size', '10GB',
         '--no-backup',
         '--project', project_id],
        check=False
    )
    
    if result.returncode != 0:
        print_error(f"Failed to create SQL instance: {result.stderr}")
        return None
    
    print_success(f"Cloud SQL instance {instance_name} created")
    
    # Set root password
    print_info("Setting root password...")
    run_command(
        ['gcloud', 'sql', 'users', 'set-password', 'postgres',
         '--instance', instance_name,
         '--password', db_password,
         '--project', project_id],
        check=False
    )
    
    # Create database
    print_info(f"Creating database: {db_name}...")
    run_command(
        ['gcloud', 'sql', 'databases', 'create', db_name,
         '--instance', instance_name,
         '--project', project_id],
        check=False
    )
    
    # Create user
    print_info(f"Creating user: {db_user}...")
    run_command(
        ['gcloud', 'sql', 'users', 'create', db_user,
         '--instance', instance_name,
         '--password', db_password,
         '--project', project_id],
        check=False
    )
    
    # Get connection name
    result = run_command(
        ['gcloud', 'sql', 'instances', 'describe', instance_name,
         '--format', 'value(connectionName)',
         '--project', project_id]
    )
    connection_name = result.stdout.strip()
    
    return connection_name


def create_service_account(sa_name: str, project_id: str, bucket_name: str) -> Optional[str]:
    """Create service account with IAM roles."""
    print_info(f"Creating service account: {sa_name}...")
    
    sa_email = f"{sa_name}@{project_id}.iam.gserviceaccount.com"
    
    # Check if exists
    result = run_command(
        ['gcloud', 'iam', 'service-accounts', 'describe', sa_email, '--project', project_id],
        check=False
    )
    if result.returncode == 0:
        print_warn(f"Service account {sa_email} already exists")
    else:
        # Create SA
        result = run_command(
            ['gcloud', 'iam', 'service-accounts', 'create', sa_name,
             '--display-name', 'RAG Service Account',
             '--project', project_id],
            check=False
        )
        if result.returncode == 0:
            print_success(f"Service account {sa_email} created")
        else:
            print_error(f"Failed to create service account: {result.stderr}")
            return None
    
    # Grant IAM roles
    print_info("Granting IAM roles...")
    roles = [
        'roles/aiplatform.user',
        'roles/cloudsql.client',
        'roles/storage.objectAdmin'
    ]
    
    for role in roles:
        result = run_command(
            ['gcloud', 'projects', 'add-iam-policy-binding', project_id,
             '--member', f'serviceAccount:{sa_email}',
             '--role', role,
             '--condition', 'None'],
            check=False,
            capture_output=True
        )
        if result.returncode == 0:
            print_success(f"  Granted {role}")
    
    # Grant Storage Admin on bucket specifically
    run_command(
        ['gcloud', 'storage', 'buckets', 'add-iam-policy-binding', f'gs://{bucket_name}',
         '--member', f'serviceAccount:{sa_email}',
         '--role', 'roles/storage.objectAdmin'],
        check=False
    )
    
    return sa_email


def save_env_file(config: dict, connection_name: str, sa_email: str):
    """Save production .env file."""
    print_info("Generating .env file...")
    
    env_content = f"""# Generated by setup_infrastructure.py
# Database connection
DATABASE_URL=postgresql+asyncpg://{config['DB_USER']}:{config['DB_PASSWORD']}@/{config['DB_NAME']}?host=/cloudsql/{connection_name}

# GCP configuration
GCP_PROJECT_ID={config['GCP_PROJECT_ID']}
GCP_REGION={config['GCP_REGION']}
GCS_BUCKET={config['GCS_BUCKET']}
CLOUD_SQL_CONNECTION_NAME={connection_name}
SERVICE_ACCOUNT_EMAIL={sa_email}

# Vertex AI
VERTEX_AI_LOCATION={config['GCP_REGION']}
EMBEDDING_MODEL=text-embedding-005
EMBEDDING_DIMENSION=768  # text-embedding-005 max
"""
    
    env_path = Path(__file__).parent.parent / '.env'
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print_success(f"Configuration saved to .env")


def save_credentials(config: dict, connection_name: str, sa_email: str):
    """Save credentials to credentials.txt."""
    print_info("Saving credentials...")
    
    creds_content = f"""RAG-as-a-Service Infrastructure Credentials
=============================================

GCP Project: {config['GCP_PROJECT_ID']}
Region: {config['GCP_REGION']}

Cloud Storage:
  Bucket: {config['GCS_BUCKET']}
  URL: https://console.cloud.google.com/storage/browser/{config['GCS_BUCKET']}

Cloud SQL:
  Instance: {config['CLOUD_SQL_INSTANCE']}
  Connection Name: {connection_name}
  Database: {config['DB_NAME']}
  User: {config['DB_USER']}
  Password: {config['DB_PASSWORD']}
  URL: https://console.cloud.google.com/sql/instances/{config['CLOUD_SQL_INSTANCE']}/overview?project={config['GCP_PROJECT_ID']}

Service Account:
  Email: {sa_email}
  Roles: aiplatform.user, cloudsql.client, storage.objectAdmin

Next steps:
1. Run: python deployment/deploy_cloudrun.py
2. Service will be available at Cloud Run URL
"""
    
    creds_path = Path(__file__).parent / 'credentials.txt'
    with open(creds_path, 'w') as f:
        f.write(creds_content)
    
    os.chmod(creds_path, 0o600)
    print_success(f"Credentials saved to deployment/credentials.txt (chmod 600)")


def main():
    """Main setup function."""
    print_info("RAG-as-a-Service Infrastructure Setup")
    print_info("=" * 50)
    
    # Check prerequisites
    print_info("Checking prerequisites...")
    if not check_gcloud_auth():
        print_error("gcloud not authenticated")
        print_info("Run: gcloud auth login")
        sys.exit(1)
    print_success("gcloud authenticated")
    
    # Load config
    config = load_config()
    print_success(f"Configuration loaded from .env.deploy")
    print_info(f"  Project: {config['GCP_PROJECT_ID']}")
    print_info(f"  Region: {config['GCP_REGION']}")
    print_info(f"  Bucket: {config['GCS_BUCKET']}")
    
    # Set project
    run_command(['gcloud', 'config', 'set', 'project', config['GCP_PROJECT_ID']])
    
    # Enable APIs
    enable_apis(config['GCP_PROJECT_ID'])
    
    # Create GCS bucket
    if not create_gcs_bucket(config['GCS_BUCKET'], config['GCP_REGION'], config['GCP_PROJECT_ID']):
        print_error("Failed to create GCS bucket")
        sys.exit(1)
    
    # Create Cloud SQL
    connection_name = create_cloud_sql_instance(
        config['CLOUD_SQL_INSTANCE'],
        config['GCP_REGION'],
        config['GCP_PROJECT_ID'],
        config['DB_NAME'],
        config['DB_USER'],
        config['DB_PASSWORD']
    )
    if not connection_name:
        print_error("Failed to create Cloud SQL instance")
        sys.exit(1)
    
    # Create Service Account
    sa_email = create_service_account(
        config['SERVICE_ACCOUNT_NAME'],
        config['GCP_PROJECT_ID'],
        config['GCS_BUCKET']
    )
    if not sa_email:
        print_error("Failed to create service account")
        sys.exit(1)
    
    # Save configuration
    save_env_file(config, connection_name, sa_email)
    save_credentials(config, connection_name, sa_email)
    
    print_info("")
    print_success("Infrastructure setup complete!")
    print_info("")
    print_info("Next steps:")
    print_info("  1. Review credentials: deployment/credentials.txt")
    print_info("  2. Deploy to Cloud Run: python deployment/deploy_cloudrun.py")
    print_info("")


if __name__ == '__main__':
    main()
