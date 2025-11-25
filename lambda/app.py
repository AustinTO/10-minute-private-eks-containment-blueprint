import base64
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import boto3
import botocore.session
from botocore.signers import RequestSigner
import urllib3
from urllib3.util import Timeout

EVIDENCE_BUCKET = os.environ["EVIDENCE_BUCKET"]
CLUSTER_NAME = os.environ["CLUSTER_NAME"]
REGION = os.environ.get("AWS_REGION", "us-east-1")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Clients inside handler to avoid freeze/thaw issues
def handler(event, context):
    # Standard Boto3 clients for non-auth ops
    eks = boto3.client("eks", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)

    detail = (event or {}).get("detail") or {}
    mode = (event or {}).get("mode") or detail.get("mode") or "audit"
    ts = int(time.time())

    try:
        cluster = eks.describe_cluster(name=CLUSTER_NAME)["cluster"]
    except Exception as exc:
        logger.exception("Failed to describe cluster")
        return {"status": "error", "error": str(exc)}

    evidence = {
        "cluster": cluster_snapshot(cluster),
        "request": {"mode": mode, "detail": detail, "ts": ts},
    }

    if mode == "containment":
        # We use the robust auth-loop logic here
        evidence["containment"] = run_containment(detail, cluster)
        key = f"runs/{ts}/containment.json"
    else:
        key = f"runs/{ts}/audit.json"

    s3.put_object(
        Bucket=EVIDENCE_BUCKET,
        Key=key,
        Body=json.dumps(evidence, indent=2).encode("utf-8"),
    )
    return {"status": "ok", "bucket": EVIDENCE_BUCKET, "key": key, "mode": mode}

def cluster_snapshot(cluster: Dict[str, Any]) -> Dict[str, Any]:
    cfg = cluster.get("resourcesVpcConfig", {})
    return {
        "name": cluster.get("name"),
        "status": cluster.get("status"),
        "version": cluster.get("version"),
        "endpointPrivate": cfg.get("endpointPrivateAccess")
    }

def run_containment(detail: Dict[str, Any], cluster: Dict[str, Any]) -> Dict[str, Any]:
    namespace = detail.get("namespace") or "default"
    logger.info("Starting containment run for namespace=%s", namespace)
    
    endpoint = cluster["endpoint"].rstrip("/")
    ca_data = cluster["certificateAuthority"]["data"]
    
    # Setup HTTP Client
    ca_path = "/tmp/eks-ca.crt"
    with open(ca_path, "wb") as f:
        f.write(base64.b64decode(ca_data))
    
    http = urllib3.PoolManager(
        cert_reqs="CERT_REQUIRED",
        ca_certs=ca_path,
        timeout=Timeout(connect=3.0, read=10.0)
    )

    # === AUTHENTICATION LOOP (The Nuclear Logic) ===
    # Attempt 1: Global
    token = get_token(CLUSTER_NAME, force_regional=False)
    if not test_auth(http, endpoint, token):
        logger.warning("Global token failed auth check. Switching to Regional...")
        
        # Attempt 2: Regional
        token = get_token(CLUSTER_NAME, force_regional=True)
        if not test_auth(http, endpoint, token):
            logger.error("Both Global and Regional tokens failed authentication.")
            raise RuntimeError("FATAL: Unable to authenticate to EKS.")
    
    logger.info("Authentication successful. Proceeding to containment.")

    # === EXECUTION ===
    return perform_containment(http, endpoint, token, namespace)

def get_token(cluster_id, force_regional=False):
    """
    Exact logic from the successful Diagnostic Script
    """
    session = botocore.session.get_session()
    client = session.create_client("sts", region_name=REGION)
    service_id = client.meta.service_model.service_id
    
    signer = RequestSigner(
        service_id=service_id,
        region_name=REGION,
        signing_name="sts",
        signature_version="v4",
        credentials=client._request_signer._credentials,
        event_emitter=session.get_component("event_emitter")
    )

    # Toggle endpoint based on strategy
    sts_host = f"sts.{REGION}.amazonaws.com" if force_regional else "sts.amazonaws.com"
    
    params = {
        "method": "GET",
        "url": f"https://{sts_host}/?Action=GetCallerIdentity&Version=2011-06-15",
        "body": {},
        "headers": {"x-k8s-aws-id": cluster_id},
        "context": {}
    }

    url = signer.generate_presigned_url(
        params, region_name=REGION, expires_in=60, operation_name=""
    )
    
    # IMPORTANT: The prefix was missing in some previous versions.
    base64_url = base64.urlsafe_b64encode(url.encode("utf-8")).decode("utf-8").rstrip("=")
    return f"k8s-aws-v1.{base64_url}"

def test_auth(http, endpoint, token):
    """
    Probes the API to see if the token is accepted.
    """
    url = f"{endpoint}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = http.request("GET", url, headers=headers)
        if r.status == 200:
            return True
        logger.warning(f"Auth Check Failed: {r.status} {r.data}")
        return False
    except Exception as e:
        logger.warning(f"Auth Check Exception: {e}")
        return False

def perform_containment(http, endpoint, token, namespace):
    policy_name = "quarantine-deny-all"
    url = f"{endpoint}/apis/networking.k8s.io/v1/namespaces/{namespace}/networkpolicies"
    
    policy = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": policy_name, "namespace": namespace},
        "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        response = http.request("POST", url, body=json.dumps(policy).encode("utf-8"), headers=headers)
        
        if response.status in [200, 201]:
            logger.info("CONTAINMENT SUCCESS: Policy Created")
            return {"status": "Containment Applied", "policy": policy_name}
        elif response.status == 409:
            logger.info("CONTAINMENT SUCCESS: Policy Already Exists")
            return {"status": "Already Contained", "policy": policy_name}
        else:
            logger.error(f"K8s Error Body: {response.data.decode('utf-8')}")
            raise RuntimeError(f"Failed: {response.status} {response.data}")
            
    except Exception as e:
        logger.exception("Policy creation failed")
        return {"status": "Error", "error": str(e)}

def dashboard_handler(event, context):
    s3 = boto3.client("s3", region_name=REGION)
    latest = None
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=EVIDENCE_BUCKET, Prefix="runs/"):
        contents = page.get("Contents") or []
        for obj in contents:
            if not latest or obj["LastModified"] > latest["LastModified"]:
                latest = obj

    if not latest:
        return {"statusCode": 200, "headers": {"Content-Type": "text/html"}, "body": "<h1>No runs yet</h1>"}

    obj = s3.get_object(Bucket=EVIDENCE_BUCKET, Key=latest["Key"])
    payload = json.loads(obj["Body"].read())

    run_ts = payload.get("request", {}).get("ts")
    run_time = datetime.utcfromtimestamp(run_ts).strftime("%Y-%m-%d %H:%M:%SZ") if run_ts else "unknown"
    mode = payload.get("request", {}).get("mode", "audit")
    
    containment_info = payload.get("containment", {})
    status_text = containment_info.get("status", "N/A")
    policy = containment_info.get("policy", "N/A")

    # CSS classes moved to simple logic to avoid syntax error
    color_style = "color: green;"
    if "Applied" in status_text or "Contained" in status_text:
        color_style = "color: red;"

    body = f"""
    <!doctype html>
    <html>
      <head><title>Containment Dashboard</title></head>
      <body style="font-family: sans-serif; margin: 2rem;">
        <div style="border: 1px solid #ccc; padding: 20px; border-radius: 8px; max-width: 600px;">
          <h1>Latest Run</h1>
          <p><strong>Time:</strong> {run_time}</p>
          <p><strong>Mode:</strong> {mode}</p>
          <p><strong>Status:</strong> <span style="{color_style}">{status_text}</span></p>
          <p><strong>Policy:</strong> {policy}</p>
          <hr>
          <small>Evidence: {latest["Key"]}</small>
        </div>
      </body>
    </html>
    """
    return {"statusCode": 200, "headers": {"Content-Type": "text/html"}, "body": body}