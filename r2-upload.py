#!/usr/bin/env python3
"""
R2 Upload Script for Cloudflare R2 Storage
Supports both direct S3-compatible uploads and Worker API uploads
Handles large files with multipart upload
"""

import os
import sys
import json
import hashlib
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import requests
from tqdm import tqdm
from dotenv import load_dotenv
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

class R2Uploader:
    def __init__(self):
        """Initialize R2 uploader with credentials from environment"""
        self.account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
        self.bucket_name = os.getenv('R2_BUCKET_NAME')
        self.access_key_id = os.getenv('R2_ACCESS_KEY_ID')
        self.secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
        self.worker_url = os.getenv('WORKER_API_BASE_URL')
        self.worker_auth = os.getenv('WORKER_AUTH_BEARER')
        self.s3_endpoint = os.getenv('R2_S3_ENDPOINT', f'https://{self.account_id}.r2.cloudflarestorage.com')
        
        # Validate configuration
        if not all([self.account_id, self.bucket_name]):
            raise ValueError("Missing required R2 configuration. Check .env file")
        
        # Initialize S3 client for R2
        if self.access_key_id and self.secret_access_key:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.s3_endpoint,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                config=Config(
                    signature_version='s3v4',
                    retries={'max_attempts': 3}
                )
            )
        else:
            self.s3_client = None
            print("Warning: S3 credentials not configured. Only Worker API uploads available.")
    
    def upload_via_s3(self, file_path: str, key: Optional[str] = None, 
                      multipart_threshold: int = 100 * 1024 * 1024) -> bool:
        """
        Upload file using S3-compatible API
        Uses multipart upload for files > threshold (default 100MB)
        """
        if not self.s3_client:
            print("S3 client not configured. Use Worker API instead.")
            return False
        
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"Error: File {file_path} not found")
            return False
        
        # Use provided key or generate from file path
        if not key:
            key = str(file_path).replace(os.sep, '/')
        
        file_size = file_path.stat().st_size
        
        try:
            # Use multipart upload for large files
            if file_size > multipart_threshold:
                print(f"Using multipart upload for {file_path.name} ({file_size / 1024 / 1024:.1f} MB)")
                return self._multipart_upload(file_path, key)
            else:
                # Regular upload for smaller files
                print(f"Uploading {file_path.name} ({file_size / 1024 / 1024:.1f} MB)")
                with open(file_path, 'rb') as f:
                    self.s3_client.put_object(
                        Bucket=self.bucket_name,
                        Key=key,
                        Body=f,
                        ContentType=mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
                    )
                print(f"✓ Uploaded {key}")
                return True
                
        except ClientError as e:
            print(f"Error uploading {file_path}: {e}")
            return False
    
    def _multipart_upload(self, file_path: Path, key: str, 
                         chunk_size: int = 10 * 1024 * 1024) -> bool:
        """
        Multipart upload for large files
        Default chunk size: 10MB
        """
        file_size = file_path.stat().st_size
        parts = []
        
        try:
            # Initiate multipart upload
            response = self.s3_client.create_multipart_upload(
                Bucket=self.bucket_name,
                Key=key,
                ContentType=mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
            )
            upload_id = response['UploadId']
            
            # Upload parts
            with open(file_path, 'rb') as f:
                with tqdm(total=file_size, unit='B', unit_scale=True, desc=file_path.name) as pbar:
                    part_number = 1
                    while True:
                        data = f.read(chunk_size)
                        if not data:
                            break
                        
                        response = self.s3_client.upload_part(
                            Bucket=self.bucket_name,
                            Key=key,
                            PartNumber=part_number,
                            UploadId=upload_id,
                            Body=data
                        )
                        
                        parts.append({
                            'PartNumber': part_number,
                            'ETag': response['ETag']
                        })
                        
                        pbar.update(len(data))
                        part_number += 1
            
            # Complete multipart upload
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket_name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            print(f"✓ Multipart upload completed for {key}")
            return True
            
        except Exception as e:
            print(f"Error in multipart upload: {e}")
            # Abort multipart upload on error
            if 'upload_id' in locals():
                try:
                    self.s3_client.abort_multipart_upload(
                        Bucket=self.bucket_name,
                        Key=key,
                        UploadId=upload_id
                    )
                except:
                    pass
            return False
    
    def upload_via_worker(self, file_path: str, key: Optional[str] = None) -> bool:
        """
        Upload file via Cloudflare Worker API
        Good for smaller files or when S3 credentials are not available
        """
        if not self.worker_url:
            print("Worker API not configured")
            return False
        
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"Error: File {file_path} not found")
            return False
        
        if not key:
            key = str(file_path).replace(os.sep, '/')
        
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_path.name, f, mimetypes.guess_type(str(file_path))[0])}
                headers = {}
                
                if self.worker_auth:
                    headers['Authorization'] = self.worker_auth
                
                response = requests.post(
                    f"{self.worker_url}/upload",
                    files=files,
                    headers=headers,
                    data={'key': key, 'bucket': self.bucket_name}
                )
                
                if response.status_code == 200:
                    print(f"✓ Uploaded {key} via Worker API")
                    return True
                else:
                    print(f"Error: Worker API returned {response.status_code}: {response.text}")
                    return False
                    
        except Exception as e:
            print(f"Error uploading via Worker: {e}")
            return False
    
    def sync_directory(self, local_dir: str, prefix: str = "", 
                      exclude_patterns: List[str] = None,
                      use_worker: bool = False,
                      max_workers: int = 5) -> Dict[str, int]:
        """
        Sync entire directory to R2
        Returns dict with upload statistics
        """
        local_dir = Path(local_dir)
        if not local_dir.is_dir():
            print(f"Error: {local_dir} is not a directory")
            return {}
        
        # Default exclude patterns
        if exclude_patterns is None:
            exclude_patterns = ['.git', '.env', '__pycache__', '*.pyc', '.DS_Store']
        
        # Collect files to upload
        files_to_upload = []
        for file_path in local_dir.rglob('*'):
            if file_path.is_file():
                # Check exclude patterns
                if any(pattern in str(file_path) for pattern in exclude_patterns):
                    continue
                
                # Calculate R2 key
                relative_path = file_path.relative_to(local_dir)
                key = f"{prefix}/{relative_path}".replace(os.sep, '/').lstrip('/')
                files_to_upload.append((file_path, key))
        
        print(f"Found {len(files_to_upload)} files to upload")
        
        # Upload files in parallel
        stats = {'success': 0, 'failed': 0, 'total_size': 0}
        failed_files = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            for file_path, key in files_to_upload:
                if use_worker:
                    future = executor.submit(self.upload_via_worker, str(file_path), key)
                else:
                    future = executor.submit(self.upload_via_s3, str(file_path), key)
                futures[future] = (file_path, key)
            
            for future in as_completed(futures):
                file_path, key = futures[future]
                try:
                    success = future.result()
                    if success:
                        stats['success'] += 1
                        stats['total_size'] += file_path.stat().st_size
                    else:
                        stats['failed'] += 1
                        failed_files.append(str(file_path))
                except Exception as e:
                    print(f"Error uploading {file_path}: {e}")
                    stats['failed'] += 1
                    failed_files.append(str(file_path))
        
        # Print summary
        print(f"\n{'='*50}")
        print(f"Upload Summary:")
        print(f"  Successful: {stats['success']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Total Size: {stats['total_size'] / 1024 / 1024:.1f} MB")
        
        if failed_files:
            print(f"\nFailed files:")
            for f in failed_files:
                print(f"  - {f}")
        
        return stats
    
    def list_objects(self, prefix: str = "", max_keys: int = 1000) -> List[Dict]:
        """List objects in R2 bucket"""
        if not self.s3_client:
            print("S3 client not configured")
            return []
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            
            objects = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    objects.append({
                        'Key': obj['Key'],
                        'Size': obj['Size'],
                        'LastModified': obj['LastModified'].isoformat()
                    })
            
            return objects
            
        except ClientError as e:
            print(f"Error listing objects: {e}")
            return []
    
    def delete_object(self, key: str) -> bool:
        """Delete object from R2"""
        if not self.s3_client:
            print("S3 client not configured")
            return False
        
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            print(f"✓ Deleted {key}")
            return True
        except ClientError as e:
            print(f"Error deleting {key}: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description='Upload files to Cloudflare R2')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Upload file command
    upload_parser = subparsers.add_parser('upload', help='Upload a file')
    upload_parser.add_argument('file', help='File to upload')
    upload_parser.add_argument('--key', help='R2 object key (default: file path)')
    upload_parser.add_argument('--worker', action='store_true', help='Use Worker API instead of S3')
    
    # Sync directory command
    sync_parser = subparsers.add_parser('sync', help='Sync directory to R2')
    sync_parser.add_argument('directory', help='Directory to sync')
    sync_parser.add_argument('--prefix', default='', help='R2 prefix for uploaded files')
    sync_parser.add_argument('--exclude', nargs='+', help='Patterns to exclude')
    sync_parser.add_argument('--worker', action='store_true', help='Use Worker API instead of S3')
    sync_parser.add_argument('--workers', type=int, default=5, help='Number of parallel uploads')
    
    # List objects command
    list_parser = subparsers.add_parser('list', help='List objects in R2')
    list_parser.add_argument('--prefix', default='', help='Prefix to filter objects')
    list_parser.add_argument('--max', type=int, default=1000, help='Maximum objects to list')
    
    # Delete object command
    delete_parser = subparsers.add_parser('delete', help='Delete object from R2')
    delete_parser.add_argument('key', help='Object key to delete')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Initialize uploader
    try:
        uploader = R2Uploader()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Please create a .env file with required configuration.")
        print("See .env.example for template.")
        return 1
    
    # Execute command
    if args.command == 'upload':
        if args.worker:
            success = uploader.upload_via_worker(args.file, args.key)
        else:
            success = uploader.upload_via_s3(args.file, args.key)
        return 0 if success else 1
    
    elif args.command == 'sync':
        stats = uploader.sync_directory(
            args.directory,
            prefix=args.prefix,
            exclude_patterns=args.exclude,
            use_worker=args.worker,
            max_workers=args.workers
        )
        return 0 if stats.get('failed', 0) == 0 else 1
    
    elif args.command == 'list':
        objects = uploader.list_objects(prefix=args.prefix, max_keys=args.max)
        if objects:
            print(f"Found {len(objects)} objects:")
            for obj in objects:
                size_mb = obj['Size'] / 1024 / 1024
                print(f"  {obj['Key']} ({size_mb:.1f} MB) - {obj['LastModified']}")
        else:
            print("No objects found")
        return 0
    
    elif args.command == 'delete':
        success = uploader.delete_object(args.key)
        return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main() or 0)