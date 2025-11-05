import os, json, time, boto3
from datetime import datetime

EVIDENCE_BUCKET = os.environ["EVIDENCE_BUCKET"]
CLUSTER_NAME    = os.environ["CLUSTER_NAME"]
REGION          = os.environ.get("AWS_REGION", "us-west-2")

s3  = boto3.client("s3", region_name=REGION)
eks = boto3.client("eks", region_name=REGION)

def handler(event, context):
    # Minimal: record request + cluster facts to S3 (works everywhere, no VPC needed)
    detail = (event or {}).get("detail") or {}
    mode   = (event or {}).get("mode") or "audit"
    ts     = int(time.time())

    try:
        cluster = eks.describe_cluster(name=CLUSTER_NAME)["cluster"]
        facts = {
            "cluster": {
                "name": cluster["name"],
                "endpointPrivate": cluster["resourcesVpcConfig"].get("endpointPrivateAccess"),
                "endpointPublic":  cluster["resourcesVpcConfig"].get("endpointPublicAccess"),
                "version": cluster.get("version"),
                "status":  cluster.get("status")
            },
            "request": { "mode": mode, "detail": detail, "ts": ts }
        }
    except Exception as e:
        facts = { "error": str(e), "request": { "mode": mode, "detail": detail, "ts": ts } }

    key = f"runs/{ts}/audit.json"
    s3.put_object(Bucket=EVIDENCE_BUCKET, Key=key, Body=json.dumps(facts, indent=2).encode("utf-8"))
    return {"status": "ok", "bucket": EVIDENCE_BUCKET, "key": key, "mode": mode}

def dashboard_handler(event, context):
    """
    Lambda Function URL entrypoint; renders a tiny HTML view of the most recent containment run.
    """
    latest = None
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=EVIDENCE_BUCKET, Prefix="runs/"):
        contents = page.get("Contents") or []
        for obj in contents:
            if not latest or obj["LastModified"] > latest["LastModified"]:
                latest = obj

    if not latest:
        body = """
        <!doctype html>
        <html>
          <head><title>Containment Dashboard</title></head>
          <body>
            <h1>Containment Dashboard</h1>
            <p>No containment runs have been recorded yet.</p>
          </body>
        </html>
        """
        return {"statusCode": 200, "headers": {"Content-Type": "text/html"}, "body": body}

    obj = s3.get_object(Bucket=EVIDENCE_BUCKET, Key=latest["Key"])
    payload = json.loads(obj["Body"].read())

    run_ts = payload.get("request", {}).get("ts")
    run_time = datetime.utcfromtimestamp(run_ts).strftime("%Y-%m-%d %H:%M:%SZ") if run_ts else "unknown"
    mode = payload.get("request", {}).get("mode", "audit")
    status = payload.get("cluster", {}).get("status", "unknown")
    version = payload.get("cluster", {}).get("version", "unknown")
    endpoint_private = payload.get("cluster", {}).get("endpointPrivate")
    endpoint_public = payload.get("cluster", {}).get("endpointPublic")

    body = f"""
    <!doctype html>
    <html>
      <head>
        <title>Containment Dashboard</title>
        <style>
          body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f7fafc; color: #1a202c; }}
          .card {{ background: white; padding: 1.5rem; border-radius: 0.75rem; box-shadow: 0 10px 30px -10px rgba(15, 23, 42, 0.25); max-width: 28rem; }}
          h1 {{ margin-bottom: 1rem; font-size: 1.75rem; }}
          dl {{ margin: 0; }}
          dt {{ font-weight: 600; margin-top: 0.75rem; }}
          dd {{ margin: 0.25rem 0 0; }}
          footer {{ margin-top: 2rem; font-size: 0.85rem; color: #4a5568; }}
        </style>
      </head>
      <body>
        <div class="card">
          <h1>Latest containment run</h1>
          <dl>
            <dt>Run time</dt>
            <dd>{run_time}</dd>
            <dt>Mode</dt>
            <dd>{mode}</dd>
            <dt>Cluster status</dt>
            <dd>{status}</dd>
            <dt>EKS version</dt>
            <dd>{version}</dd>
            <dt>Private endpoint</dt>
            <dd>{endpoint_private}</dd>
            <dt>Public endpoint</dt>
            <dd>{endpoint_public}</dd>
          </dl>
          <footer>Evidence object: <code>{latest["Key"]}</code></footer>
        </div>
      </body>
    </html>
    """

    return {"statusCode": 200, "headers": {"Content-Type": "text/html"}, "body": body}
