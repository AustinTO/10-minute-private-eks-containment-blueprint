import os, json, time, boto3

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
