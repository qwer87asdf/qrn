/**
 * Cloudflare Worker for R2 Upload
 * Deploy this to your Cloudflare account to enable uploads without S3 credentials
 * 
 * Environment variables to set in Worker:
 * - R2_BUCKET: Your R2 bucket binding
 * - AUTH_TOKEN: Bearer token for authentication (optional but recommended)
 */

export default {
  async fetch(request, env, ctx) {
    // CORS headers
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    };

    // Handle preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    // Check authentication if configured
    if (env.AUTH_TOKEN) {
      const authHeader = request.headers.get('Authorization');
      if (!authHeader || authHeader !== `Bearer ${env.AUTH_TOKEN}`) {
        return new Response('Unauthorized', { 
          status: 401,
          headers: corsHeaders 
        });
      }
    }

    const url = new URL(request.url);
    const path = url.pathname;

    try {
      // Route handlers
      if (path === '/upload' && request.method === 'POST') {
        return await handleUpload(request, env, corsHeaders);
      } else if (path === '/multipart/init' && request.method === 'POST') {
        return await handleMultipartInit(request, env, corsHeaders);
      } else if (path === '/multipart/upload' && request.method === 'POST') {
        return await handleMultipartUpload(request, env, corsHeaders);
      } else if (path === '/multipart/complete' && request.method === 'POST') {
        return await handleMultipartComplete(request, env, corsHeaders);
      } else if (path === '/presigned' && request.method === 'POST') {
        return await handlePresignedUrl(request, env, corsHeaders);
      } else if (path === '/list' && request.method === 'GET') {
        return await handleList(request, env, corsHeaders);
      } else if (path.startsWith('/download/') && request.method === 'GET') {
        return await handleDownload(request, env, corsHeaders);
      } else {
        return new Response('Not Found', { 
          status: 404,
          headers: corsHeaders 
        });
      }
    } catch (error) {
      console.error('Worker error:', error);
      return new Response(`Error: ${error.message}`, { 
        status: 500,
        headers: corsHeaders 
      });
    }
  }
};

// Handle single file upload
async function handleUpload(request, env, corsHeaders) {
  try {
    const formData = await request.formData();
    const file = formData.get('file');
    const key = formData.get('key') || file.name;
    const bucket = formData.get('bucket') || 'default';
    
    if (!file) {
      return new Response('No file provided', { 
        status: 400,
        headers: corsHeaders 
      });
    }

    // Check file size (Cloudflare Worker limit ~100MB per request)
    const arrayBuffer = await file.arrayBuffer();
    if (arrayBuffer.byteLength > 100 * 1024 * 1024) {
      return new Response('File too large. Use multipart upload for files >100MB', { 
        status: 413,
        headers: corsHeaders 
      });
    }

    // Upload to R2
    const r2Object = await env.R2_BUCKET.put(key, arrayBuffer, {
      httpMetadata: {
        contentType: file.type || 'application/octet-stream',
      },
      customMetadata: {
        uploadedAt: new Date().toISOString(),
        originalName: file.name,
        size: arrayBuffer.byteLength.toString(),
      }
    });

    return new Response(JSON.stringify({
      success: true,
      key: key,
      size: arrayBuffer.byteLength,
      etag: r2Object.etag,
      version: r2Object.version,
    }), {
      status: 200,
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
      }
    });
  } catch (error) {
    console.error('Upload error:', error);
    return new Response(`Upload failed: ${error.message}`, { 
      status: 500,
      headers: corsHeaders 
    });
  }
}

// Initialize multipart upload (store in KV or Durable Object)
async function handleMultipartInit(request, env, corsHeaders) {
  const data = await request.json();
  const { key, uploadId, totalParts } = data;
  
  // For simplicity, we'll use the uploadId as is
  // In production, you'd want to store this in KV or Durable Objects
  
  return new Response(JSON.stringify({
    success: true,
    uploadId: uploadId,
    key: key,
  }), {
    headers: {
      ...corsHeaders,
      'Content-Type': 'application/json',
    }
  });
}

// Handle multipart chunk upload
async function handleMultipartUpload(request, env, corsHeaders) {
  try {
    const formData = await request.formData();
    const chunk = formData.get('chunk');
    const uploadId = formData.get('uploadId');
    const partNumber = formData.get('partNumber');
    const key = formData.get('key');
    
    if (!chunk || !uploadId || !partNumber) {
      return new Response('Missing required fields', { 
        status: 400,
        headers: corsHeaders 
      });
    }

    // Store chunk temporarily
    // In production, you'd accumulate these and combine them
    const chunkKey = `multipart/${uploadId}/part${partNumber}`;
    const arrayBuffer = await chunk.arrayBuffer();
    
    await env.R2_BUCKET.put(chunkKey, arrayBuffer, {
      customMetadata: {
        uploadId: uploadId,
        partNumber: partNumber.toString(),
        originalKey: key,
      }
    });

    return new Response(JSON.stringify({
      success: true,
      partNumber: partNumber,
      size: arrayBuffer.byteLength,
    }), {
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
      }
    });
  } catch (error) {
    console.error('Multipart upload error:', error);
    return new Response(`Chunk upload failed: ${error.message}`, { 
      status: 500,
      headers: corsHeaders 
    });
  }
}

// Complete multipart upload
async function handleMultipartComplete(request, env, corsHeaders) {
  try {
    const data = await request.json();
    const { key, uploadId } = data;
    
    // List all parts for this upload
    const prefix = `multipart/${uploadId}/`;
    const parts = await env.R2_BUCKET.list({ prefix: prefix });
    
    if (!parts.objects || parts.objects.length === 0) {
      return new Response('No parts found for upload', { 
        status: 400,
        headers: corsHeaders 
      });
    }

    // Combine all parts
    const chunks = [];
    for (const part of parts.objects) {
      const obj = await env.R2_BUCKET.get(part.key);
      if (obj) {
        chunks.push(await obj.arrayBuffer());
      }
    }

    // Combine chunks into single file
    const combinedSize = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
    const combined = new Uint8Array(combinedSize);
    let offset = 0;
    
    for (const chunk of chunks) {
      combined.set(new Uint8Array(chunk), offset);
      offset += chunk.byteLength;
    }

    // Upload combined file
    await env.R2_BUCKET.put(key, combined.buffer, {
      customMetadata: {
        uploadedAt: new Date().toISOString(),
        uploadType: 'multipart',
        parts: parts.objects.length.toString(),
      }
    });

    // Clean up parts
    for (const part of parts.objects) {
      await env.R2_BUCKET.delete(part.key);
    }

    return new Response(JSON.stringify({
      success: true,
      key: key,
      size: combinedSize,
      parts: parts.objects.length,
    }), {
      headers: {
        ...corsHeaders,
        'Content-Type': 'application/json',
      }
    });
  } catch (error) {
    console.error('Multipart complete error:', error);
    return new Response(`Complete failed: ${error.message}`, { 
      status: 500,
      headers: corsHeaders 
    });
  }
}

// Generate presigned URL (R2 doesn't support this directly, so we simulate it)
async function handlePresignedUrl(request, env, corsHeaders) {
  const data = await request.json();
  const { key, contentType } = data;
  
  // Generate a temporary upload URL
  // In production, you'd want to implement proper signed URLs
  const uploadUrl = `${request.url.replace('/presigned', '/upload')}`;
  
  return new Response(JSON.stringify({
    url: uploadUrl,
    method: 'POST',
    fields: {
      key: key,
      contentType: contentType,
    }
  }), {
    headers: {
      ...corsHeaders,
      'Content-Type': 'application/json',
    }
  });
}

// List objects in bucket
async function handleList(request, env, corsHeaders) {
  const url = new URL(request.url);
  const prefix = url.searchParams.get('prefix') || '';
  const limit = parseInt(url.searchParams.get('limit') || '1000');
  
  const list = await env.R2_BUCKET.list({
    prefix: prefix,
    limit: limit,
  });

  const objects = list.objects.map(obj => ({
    key: obj.key,
    size: obj.size,
    etag: obj.etag,
    uploaded: obj.uploaded.toISOString(),
  }));

  return new Response(JSON.stringify({
    objects: objects,
    truncated: list.truncated,
    cursor: list.cursor,
  }), {
    headers: {
      ...corsHeaders,
      'Content-Type': 'application/json',
    }
  });
}

// Download file
async function handleDownload(request, env, corsHeaders) {
  const url = new URL(request.url);
  const key = url.pathname.replace('/download/', '');
  
  const object = await env.R2_BUCKET.get(key);
  
  if (!object) {
    return new Response('Not found', { 
      status: 404,
      headers: corsHeaders 
    });
  }

  const headers = new Headers(object.httpMetadata || {});
  headers.set('etag', object.etag);
  Object.entries(corsHeaders).forEach(([k, v]) => headers.set(k, v));
  
  return new Response(object.body, { headers });
}