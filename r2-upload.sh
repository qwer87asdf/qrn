#!/bin/bash

# Simple R2 upload script using AWS CLI (S3-compatible)
# Requires: aws-cli configured with R2 credentials

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Configuration
BUCKET="${R2_BUCKET_NAME}"
ENDPOINT="${R2_S3_ENDPOINT}"
PROFILE="r2"  # AWS CLI profile name for R2

# Function to setup AWS CLI for R2
setup_r2_profile() {
    echo "Setting up AWS CLI profile for R2..."
    
    aws configure set aws_access_key_id "${R2_ACCESS_KEY_ID}" --profile "${PROFILE}"
    aws configure set aws_secret_access_key "${R2_SECRET_ACCESS_KEY}" --profile "${PROFILE}"
    aws configure set region "auto" --profile "${PROFILE}"
    
    echo "✓ R2 profile configured"
}

# Function to upload a single file
upload_file() {
    local file="$1"
    local key="${2:-$file}"
    
    if [ ! -f "$file" ]; then
        echo "Error: File $file not found"
        return 1
    fi
    
    local file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
    local size_mb=$((file_size / 1048576))
    
    echo "Uploading $file (${size_mb} MB) to s3://${BUCKET}/${key}"
    
    # Use multipart upload for files > 100MB
    if [ $size_mb -gt 100 ]; then
        aws s3 cp "$file" "s3://${BUCKET}/${key}" \
            --endpoint-url="${ENDPOINT}" \
            --profile="${PROFILE}" \
            --storage-class STANDARD \
            --metadata "uploaded=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    else
        aws s3api put-object \
            --bucket "${BUCKET}" \
            --key "${key}" \
            --body "$file" \
            --endpoint-url="${ENDPOINT}" \
            --profile="${PROFILE}" \
            --metadata "uploaded=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    fi
    
    if [ $? -eq 0 ]; then
        echo "✓ Uploaded successfully"
        return 0
    else
        echo "✗ Upload failed"
        return 1
    fi
}

# Function to sync directory
sync_directory() {
    local dir="$1"
    local prefix="${2:-}"
    
    if [ ! -d "$dir" ]; then
        echo "Error: Directory $dir not found"
        return 1
    fi
    
    echo "Syncing $dir to s3://${BUCKET}/${prefix}"
    
    aws s3 sync "$dir" "s3://${BUCKET}/${prefix}" \
        --endpoint-url="${ENDPOINT}" \
        --profile="${PROFILE}" \
        --exclude ".git/*" \
        --exclude ".env" \
        --exclude "*.pyc" \
        --exclude ".DS_Store" \
        --exclude "__pycache__/*" \
        --storage-class STANDARD
    
    if [ $? -eq 0 ]; then
        echo "✓ Sync completed successfully"
        return 0
    else
        echo "✗ Sync failed"
        return 1
    fi
}

# Function to list objects
list_objects() {
    local prefix="${1:-}"
    
    echo "Listing objects in s3://${BUCKET}/${prefix}"
    
    aws s3 ls "s3://${BUCKET}/${prefix}" \
        --endpoint-url="${ENDPOINT}" \
        --profile="${PROFILE}" \
        --recursive \
        --human-readable \
        --summarize
}

# Function to upload large tar.gz files from repo
upload_large_files() {
    echo "Searching for large tar.gz files..."
    
    # Find all tar.gz files
    find . -name "*.tar.gz" -type f | while read -r file; do
        local file_size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
        local size_mb=$((file_size / 1048576))
        
        if [ $size_mb -gt 50 ]; then
            echo "Found large file: $file (${size_mb} MB)"
            local key="large-files/${file#./}"
            upload_file "$file" "$key"
        fi
    done
}

# Main script
main() {
    local command="$1"
    shift
    
    case "$command" in
        setup)
            setup_r2_profile
            ;;
        upload)
            upload_file "$@"
            ;;
        sync)
            sync_directory "$@"
            ;;
        list)
            list_objects "$@"
            ;;
        upload-large)
            upload_large_files
            ;;
        sync-repo)
            # Sync entire repository
            sync_directory "." "qrn-repo"
            ;;
        help|*)
            echo "Usage: $0 <command> [options]"
            echo ""
            echo "Commands:"
            echo "  setup              Setup AWS CLI profile for R2"
            echo "  upload <file>      Upload a single file"
            echo "  sync <dir>         Sync a directory to R2"
            echo "  list [prefix]      List objects in bucket"
            echo "  upload-large       Find and upload large tar.gz files"
            echo "  sync-repo          Sync entire repository to R2"
            echo ""
            echo "Examples:"
            echo "  $0 setup"
            echo "  $0 upload common/mushaf_1.tar.gz"
            echo "  $0 sync . qrn-backup"
            echo "  $0 upload-large"
            echo "  $0 sync-repo"
            ;;
    esac
}

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed"
    echo "Install it with: pip install awscli or brew install awscli"
    exit 1
fi

# Check if .env exists
if [ ! -f .env ]; then
    echo "Warning: .env file not found. Creating from template..."
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "Please edit .env with your R2 credentials"
        exit 1
    fi
fi

# Run main function
main "$@"