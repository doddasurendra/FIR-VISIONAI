import os
import mimetypes
import httpx
from app.config import settings

def sync_storage():
    supabase_url = settings.SUPABASE_URL
    service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_KEY
    bucket = settings.SUPABASE_STORAGE_BUCKET or "evidence"
    evidence_dir = settings.EVIDENCE_DIR

    if not supabase_url or not service_role_key:
        print("[ERROR] SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured in .env")
        return

    files = [f for f in os.listdir(evidence_dir) if os.path.isfile(os.path.join(evidence_dir, f))]
    print(f"Uploading {len(files)} evidence files to Supabase bucket '{bucket}'...")
    uploaded = 0
    with httpx.Client(timeout=30.0) as client:
        for fname in files:
            fpath = os.path.join(evidence_dir, fname)
            ctype, _ = mimetypes.guess_type(fname)
            ctype = ctype or "application/octet-stream"
            with open(fpath, "rb") as fp:
                file_bytes = fp.read()
            url = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{fname}"
            headers = {
                "Authorization": f"Bearer {service_role_key}",
                "Content-Type": ctype,
                "x-upsert": "true"
            }
            resp = client.post(url, content=file_bytes, headers=headers)
            if resp.status_code in (200, 201):
                uploaded += 1
                print(f"  + Uploaded: {fname}")
            else:
                print(f"  ! Error uploading {fname}: {resp.status_code} {resp.text}")
    print(f"Total uploaded to Supabase Storage: {uploaded}/{len(files)}")

if __name__ == "__main__":
    sync_storage()
