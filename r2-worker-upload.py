#!/usr/bin/env python3
"""
R2 Upload via Cloudflare Worker API
No S3 credentials required - uses Worker endpoint with Bearer auth
"""

import os
import sys
import json
import mimetypes
from pathlib import Path
from typing import Optional, List, Dict
import requests
from tqdm import tqdm
from dotenv import load_dotenv
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

# Load environment variables
load_dotenv()

class R2WorkerUploader:
    def __init__(self):
        """Initialize uploader with Worker API credentials"""
        self.account_id = os.getenv('CLOUDFLARE_ACCOUNT_ID')
        self.bucket_name = os.getenv('R2_BUCKET_NAME')
        self.worker_url = os.getenv('WORKER_API_BASE_URL')
        self.worker_auth = os.getenv('WORKER_AUTH_BEARER')
        
        # Validate configuration
        if not all([self.worker_url]):
            raise ValueError("Missing WORKER_API_BASE_URL in .env file")
        
        print(f"Using Worker API: {self.worker_url}")
        if self.worker_auth:
            print("✓ Authorization configured")
    
    def upload_file(self, file_path: str, key: Optional[str] = None,
                   chunk_size: int = 50 * 1024 * 1024) -> bool:
        """
        Upload file via Worker API
        For large files, splits into chunks
        """
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"Error: File {file_path} not found")
            return False
        
        if not key:
            key = str(file_path).replace(os.sep, '/')
        
        file_size = file_path.stat().st_size
        size_mb = file_size / 1024 / 1024
        
        print(f"Uploading {file_path.name} ({size_mb:.1f} MB)")
        
        try:
            # For large files, use chunked upload
            if file_size > chunk_size:
                return self._chunked_upload(file_path, key, chunk_size)
            else:
                return self._simple_upload(file_path, key)
                
        except Exception as e:
            print(f"Error uploading {file_path}: {e}")
            return False
    
    def _simple_upload(self, file_path: Path, key: str) -> bool:
        """Simple upload for smaller files"""
        try:
            with open(file_path, 'rb') as f:
                files = {
                    'file': (file_path.name, f, mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream')
                }
                
                headers = {}
                if self.worker_auth:
                    headers['Authorization'] = self.worker_auth
                
                data = {
                    'key': key,
                    'bucket': self.bucket_name or 'default'
                }
                
                response = requests.post(
                    f"{self.worker_url}/upload",
                    files=files,
                    headers=headers,
                    data=data,
                    timeout=300  # 5 minute timeout
                )
                
                if response.status_code in [200, 201]:
                    print(f"✓ Uploaded {key}")
                    return True
                else:
                    print(f"Error: Worker returned {response.status_code}: {response.text[:200]}")
                    return False
                    
        except requests.exceptions.Timeout:
            print("Upload timed out. File may be too large for single upload.")
            print("Trying chunked upload...")
            return self._chunked_upload(file_path, key, 10 * 1024 * 1024)
        except Exception as e:
            print(f"Error in upload: {e}")
            return False
    
    def _chunked_upload(self, file_path: Path, key: str, 
                       chunk_size: int = 10 * 1024 * 1024) -> bool:
        """
        Upload file in chunks for large files
        Requires Worker to support multipart upload
        """
        file_size = file_path.stat().st_size
        chunks = (file_size + chunk_size - 1) // chunk_size
        
        print(f"Uploading in {chunks} chunks...")
        
        # Generate upload ID
        upload_id = hashlib.md5(f"{key}-{file_size}".encode()).hexdigest()
        
        headers = {}
        if self.worker_auth:
            headers['Authorization'] = self.worker_auth
        
        try:
            # Initialize multipart upload
            init_response = requests.post(
                f"{self.worker_url}/multipart/init",
                headers=headers,
                json={
                    'key': key,
                    'bucket': self.bucket_name or 'default',
                    'uploadId': upload_id,
                    'totalParts': chunks
                }
            )
            
            if init_response.status_code not in [200, 201]:
                # Fallback to simple upload if multipart not supported
                print("Worker doesn't support multipart. Trying single upload...")
                return self._simple_upload(file_path, key)
            
            # Upload chunks
            with open(file_path, 'rb') as f:
                with tqdm(total=file_size, unit='B', unit_scale=True, desc="Uploading") as pbar:
                    for part_number in range(1, chunks + 1):
                        chunk_data = f.read(chunk_size)
                        if not chunk_data:
                            break
                        
                        # Upload chunk
                        part_response = requests.post(
                            f"{self.worker_url}/multipart/upload",
                            headers=headers,
                            files={'chunk': (f"part{part_number}", chunk_data)},
                            data={
                                'key': key,
                                'uploadId': upload_id,
                                'partNumber': part_number
                            }
                        )
                        
                        if part_response.status_code not in [200, 201]:
                            print(f"Error uploading part {part_number}: {part_response.status_code}")
                            return False
                        
                        pbar.update(len(chunk_data))
            
            # Complete multipart upload
            complete_response = requests.post(
                f"{self.worker_url}/multipart/complete",
                headers=headers,
                json={
                    'key': key,
                    'uploadId': upload_id,
                    'bucket': self.bucket_name or 'default'
                }
            )
            
            if complete_response.status_code in [200, 201]:
                print(f"✓ Multipart upload completed for {key}")
                return True
            else:
                print(f"Error completing upload: {complete_response.status_code}")
                return False
                
        except Exception as e:
            print(f"Error in chunked upload: {e}")
            print("Note: Your Worker may not support multipart uploads for very large files")
            return False
    
    def upload_via_presigned_url(self, file_path: str, key: Optional[str] = None) -> bool:
        """
        Alternative: Get presigned URL from Worker and upload directly
        """
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"Error: File {file_path} not found")
            return False
        
        if not key:
            key = str(file_path).replace(os.sep, '/')
        
        headers = {}
        if self.worker_auth:
            headers['Authorization'] = self.worker_auth
        
        try:
            # Request presigned URL from Worker
            response = requests.post(
                f"{self.worker_url}/presigned",
                headers=headers,
                json={
                    'key': key,
                    'bucket': self.bucket_name or 'default',
                    'contentType': mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
                }
            )
            
            if response.status_code != 200:
                print(f"Error getting presigned URL: {response.status_code}")
                return False
            
            presigned_data = response.json()
            upload_url = presigned_data.get('url')
            
            if not upload_url:
                print("No presigned URL returned")
                return False
            
            # Upload directly to presigned URL
            print(f"Uploading {file_path.name} via presigned URL...")
            
            with open(file_path, 'rb') as f:
                upload_response = requests.put(
                    upload_url,
                    data=f,
                    headers={
                        'Content-Type': mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
                    }
                )
                
                if upload_response.status_code in [200, 201]:
                    print(f"✓ Uploaded {key} via presigned URL")
                    return True
                else:
                    print(f"Upload failed: {upload_response.status_code}")
                    return False
                    
        except Exception as e:
            print(f"Error with presigned URL upload: {e}")
            return False
    
    def sync_directory(self, local_dir: str, prefix: str = "",
                      exclude_patterns: List[str] = None,
                      max_workers: int = 3) -> Dict[str, int]:
        """
        Sync directory to R2 via Worker API
        Note: Limited parallelism to avoid overwhelming Worker
        """
        local_dir = Path(local_dir)
        if not local_dir.is_dir():
            print(f"Error: {local_dir} is not a directory")
            return {}
        
        # Default exclude patterns
        if exclude_patterns is None:
            exclude_patterns = ['.git', '.env', '__pycache__', '*.pyc', '.DS_Store', 'node_modules']
        
        # Collect files to upload
        files_to_upload = []
        total_size = 0
        
        for file_path in local_dir.rglob('*'):
            if file_path.is_file():
                # Check exclude patterns
                if any(pattern in str(file_path) for pattern in exclude_patterns):
                    continue
                
                # Skip very large files (>500MB) - these need special handling
                file_size = file_path.stat().st_size
                if file_size > 500 * 1024 * 1024:
                    print(f"⚠ Skipping very large file (>500MB): {file_path.name}")
                    print(f"  Upload this separately: python r2-worker-upload.py upload '{file_path}'")
                    continue
                
                # Calculate R2 key
                relative_path = file_path.relative_to(local_dir)
                key = f"{prefix}/{relative_path}".replace(os.sep, '/').lstrip('/')
                files_to_upload.append((file_path, key))
                total_size += file_size
        
        print(f"Found {len(files_to_upload)} files to upload ({total_size / 1024 / 1024:.1f} MB total)")
        
        # Upload files with limited parallelism
        stats = {'success': 0, 'failed': 0}
        failed_files = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            
            for file_path, key in files_to_upload:
                future = executor.submit(self.upload_file, str(file_path), key)
                futures[future] = (file_path, key)
            
            with tqdm(total=len(files_to_upload), desc="Uploading files") as pbar:
                for future in as_completed(futures):
                    file_path, key = futures[future]
                    try:
                        success = future.result()
                        if success:
                            stats['success'] += 1
                        else:
                            stats['failed'] += 1
                            failed_files.append(str(file_path))
                    except Exception as e:
                        print(f"\nError uploading {file_path}: {e}")
                        stats['failed'] += 1
                        failed_files.append(str(file_path))
                    pbar.update(1)
        
        # Print summary
        print(f"\n{'='*50}")
        print(f"Upload Summary:")
        print(f"  Successful: {stats['success']}")
        print(f"  Failed: {stats['failed']}")
        
        if failed_files:
            print(f"\nFailed files:")
            for f in failed_files[:10]:  # Show first 10
                print(f"  - {f}")
            if len(failed_files) > 10:
                print(f"  ... and {len(failed_files) - 10} more")
        
        return stats

def main():
    parser = argparse.ArgumentParser(description='Upload files to R2 via Cloudflare Worker')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Upload file command
    upload_parser = subparsers.add_parser('upload', help='Upload a file')
    upload_parser.add_argument('file', help='File to upload')
    upload_parser.add_argument('--key', help='R2 object key (default: file path)')
    upload_parser.add_argument('--presigned', action='store_true', 
                              help='Use presigned URL method')
    
    # Sync directory command
    sync_parser = subparsers.add_parser('sync', help='Sync directory to R2')
    sync_parser.add_argument('directory', help='Directory to sync')
    sync_parser.add_argument('--prefix', default='', help='R2 prefix for uploaded files')
    sync_parser.add_argument('--exclude', nargs='+', help='Patterns to exclude')
    sync_parser.add_argument('--workers', type=int, default=3, 
                            help='Number of parallel uploads (default: 3)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        print("\nExamples:")
        print("  python r2-worker-upload.py upload large-file.tar.gz")
        print("  python r2-worker-upload.py upload file.zip --key backups/file.zip")
        print("  python r2-worker-upload.py sync . --prefix repo-backup")
        return
    
    # Initialize uploader
    try:
        uploader = R2WorkerUploader()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nCreate a .env file with:")
        print("WORKER_API_BASE_URL=https://your-worker.workers.dev")
        print("WORKER_AUTH_BEARER=Bearer your_token_here")
        print("R2_BUCKET_NAME=your-bucket (optional)")
        return 1
    
    # Execute command
    if args.command == 'upload':
        if args.presigned:
            success = uploader.upload_via_presigned_url(args.file, args.key)
        else:
            success = uploader.upload_file(args.file, args.key)
        return 0 if success else 1
    
    elif args.command == 'sync':
        stats = uploader.sync_directory(
            args.directory,
            prefix=args.prefix,
            exclude_patterns=args.exclude,
            max_workers=args.workers
        )
        return 0 if stats.get('failed', 0) == 0 else 1

if __name__ == '__main__':
    sys.exit(main() or 0)