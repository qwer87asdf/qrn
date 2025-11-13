# R2 Upload Tools for Large Files and Repository Backup

This repository includes tools to upload large files (>100MB) and sync your entire repository to Cloudflare R2.

## Setup

### 1. Configure Credentials

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:
- `CLOUDFLARE_ACCOUNT_ID`: Your Cloudflare account ID
- `R2_BUCKET_NAME`: Your R2 bucket name
- `R2_ACCESS_KEY_ID`: R2 access key (get from Cloudflare dashboard)
- `R2_SECRET_ACCESS_KEY`: R2 secret key
- `WORKER_API_BASE_URL`: (Optional) Your Worker URL for API uploads
- `WORKER_AUTH_BEARER`: (Optional) Bearer token for Worker auth

### 2. Install Dependencies

#### For Python Script:
```bash
pip install -r requirements.txt
```

#### For Shell Script:
```bash
# Install AWS CLI
pip install awscli
# or
brew install awscli
```

## Usage

### Python Script (`r2-upload.py`)

#### Upload a single file:
```bash
# Upload file (auto-handles large files with multipart)
python r2-upload.py upload common/mushaf_1.tar.gz

# Upload with custom key
python r2-upload.py upload large-file.tar.gz --key backups/large-file.tar.gz

# Upload via Worker API (for smaller files)
python r2-upload.py upload file.txt --worker
```

#### Sync entire repository:
```bash
# Sync current directory to R2
python r2-upload.py sync . --prefix qrn-repo

# Sync with parallel uploads
python r2-upload.py sync . --prefix qrn-backup --workers 10

# Exclude certain patterns
python r2-upload.py sync . --prefix repo --exclude .git "*.log" node_modules
```

#### List objects in R2:
```bash
python r2-upload.py list
python r2-upload.py list --prefix qrn-repo/
```

#### Delete an object:
```bash
python r2-upload.py delete path/to/file.tar.gz
```

### Shell Script (`r2-upload.sh`)

Make it executable first:
```bash
chmod +x r2-upload.sh
```

#### Setup AWS CLI for R2:
```bash
./r2-upload.sh setup
```

#### Upload operations:
```bash
# Upload single file
./r2-upload.sh upload common/mushaf_1.tar.gz

# Upload all large tar.gz files (>50MB)
./r2-upload.sh upload-large

# Sync entire repository
./r2-upload.sh sync-repo

# Sync specific directory
./r2-upload.sh sync common/ common-backup

# List objects
./r2-upload.sh list
```

## Handling Large Files (>100MB)

Both scripts automatically handle large files:

1. **Python script**: Uses multipart upload for files >100MB
2. **Shell script**: Automatically uses AWS S3 multipart upload for large files

### Upload your large tar.gz files:
```bash
# Find and upload all large files
python r2-upload.py upload common/mushaf_1.tar.gz
python r2-upload.py upload common/mushaf_2.tar.gz

# Or use shell script
./r2-upload.sh upload-large
```

## Sync Repository to R2

To backup your entire repository (excluding .git and other unnecessary files):

```bash
# Using Python (recommended for large repos)
python r2-upload.py sync . --prefix qrn-$(date +%Y%m%d)

# Using shell script
./r2-upload.sh sync-repo
```

## Direct S3-Compatible Access

You can also use standard S3 tools with R2:

```bash
# Configure AWS CLI
aws configure --profile r2
# Enter your R2 credentials

# Upload with AWS CLI
aws s3 cp large-file.tar.gz s3://your-bucket/ \
    --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com \
    --profile r2

# Sync directory
aws s3 sync . s3://your-bucket/backup/ \
    --endpoint-url https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com \
    --profile r2 \
    --exclude ".git/*"
```

## Worker API Upload (Optional)

If you have a Cloudflare Worker set up for uploads:

```javascript
// Example Worker code
export default {
  async fetch(request, env) {
    if (request.method === 'POST' && new URL(request.url).pathname === '/upload') {
      const formData = await request.formData();
      const file = formData.get('file');
      const key = formData.get('key') || file.name;
      
      await env.R2_BUCKET.put(key, file.stream());
      
      return new Response('Upload successful', { status: 200 });
    }
    return new Response('Not found', { status: 404 });
  }
};
```

Then use:
```bash
python r2-upload.py upload file.txt --worker
```

## Tips

1. **For files 50-100MB**: These work with regular Git but R2 is recommended for better performance
2. **For files >100MB**: Must use R2 or Git LFS
3. **Parallel uploads**: Use `--workers` flag to speed up directory sync
4. **Bandwidth**: R2 has generous free tier (10GB/month) and cheap bandwidth ($0.015/GB)

## Troubleshooting

1. **"Missing required R2 configuration"**: Check your `.env` file has all required fields
2. **"Access Denied"**: Verify your R2 access keys have correct permissions
3. **Slow uploads**: Increase workers for parallel uploads or use multipart for large files
4. **Worker API fails**: Check CORS settings and authentication token

## Cost Estimation

Cloudflare R2 pricing:
- Storage: $0.015/GB/month
- Class A operations (uploads): $4.50/million requests
- Class B operations (downloads): $0.36/million requests
- No bandwidth charges for downloads!