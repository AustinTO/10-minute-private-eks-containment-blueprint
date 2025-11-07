import base64
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import boto3
import botocore.session
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import urllib3
from urllib3.util import Timeout

EVIDENCE_BUCKET = os.environ["EVIDENCE_BUCKET"]
CLUSTER_NAME = os.environ["CLUSTER_NAME"]
ROLE_ARN = os.environ.get("LAMBDA_ROLE_ARN", "")
SERVICE_ACCOUNT_NAMESPACE = os.environ.get("RBAC_NAMESPACE", "kube-system")
SERVICE_ACCOUNT_NAME = os.environ.get("RBAC_SERVICE_ACCOUNT", "containment-lambda")
CLUSTER_ROLE_NAME = os.environ.get("RBAC_CLUSTER_ROLE", "containment-lambda")
CLUSTER_ROLE_BINDING_NAME = os.environ.get("RBAC_CLUSTER_ROLE_BINDING", "containment-lambda")
#test touch
SESSION = boto3.session.Session()
REGION = (
    os.environ.get("AWS_REGION")
    or os.environ.get("AWS_DEFAULT_REGION")
    or SESSION.region_name
    or "us-east-1"
)

s3 = SESSION.client("s3", region_name=REGION)
eks = SESSION.client("eks", region_name=REGION)

HTTP_TIMEOUT = Timeout(connect=3.0, read=10.0)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ResourceNotFound(Exception):
    pass


def handler(event, context):
    detail = (event or {}).get("detail") or {}
    mode = (event or {}).get("mode") or detail.get("mode") or "audit"
    ts = int(time.time())

    try:
        cluster = eks.describe_cluster(name=CLUSTER_NAME)["cluster"]
    except Exception as exc:  # pragma: no cover - surfaced in evidence
        logger.exception("Failed to describe cluster")
        payload = {
            "error": str(exc),
            "request": {"mode": mode, "detail": detail, "ts": ts},
        }
        key = f"runs/{ts}/error.json"
        put_evidence(key, payload)
        return {"status": "error", "bucket": EVIDENCE_BUCKET, "key": key, "mode": mode}

    evidence = {
        "cluster": cluster_snapshot(cluster),
        "request": {"mode": mode, "detail": detail, "ts": ts},
    }

    if mode == "containment":
        evidence["containment"] = run_containment(detail, cluster)
        key = f"runs/{ts}/containment.json"
    else:
        key = f"runs/{ts}/audit.json"

    put_evidence(key, evidence)
    return {"status": "ok", "bucket": EVIDENCE_BUCKET, "key": key, "mode": mode}


def cluster_snapshot(cluster: Dict[str, Any]) -> Dict[str, Any]:
    cfg = cluster.get("resourcesVpcConfig", {})
    return {
        "name": cluster.get("name"),
        "status": cluster.get("status"),
        "version": cluster.get("version"),
        "endpointPrivate": cfg.get("endpointPrivateAccess"),
        "endpointPublic": cfg.get("endpointPublicAccess"),
    }


def put_evidence(key: str, body: Dict[str, Any]) -> None:
    s3.put_object(
        Bucket=EVIDENCE_BUCKET,
        Key=key,
        Body=json.dumps(body, indent=2).encode("utf-8"),
    )


def run_containment(detail: Dict[str, Any], cluster: Dict[str, Any]) -> Dict[str, Any]:
    namespace = detail.get("namespace") or "default"
    logger.info("Starting containment run for namespace=%s", namespace)
    ca_path = write_ca_file(cluster["certificateAuthority"]["data"])
    token = build_bearer_token(CLUSTER_NAME)
    http = urllib3.PoolManager(
        cert_reqs="CERT_REQUIRED",
        ca_certs=ca_path,
        timeout=HTTP_TIMEOUT,
    )
    endpoint = cluster["endpoint"].rstrip("/")

    summary = {"namespace": namespace}

    try:
        rbac = ensure_rbac(endpoint, http, token)
        actions = perform_containment(endpoint, http, token, namespace)
        summary.update({"status": "ok", "rbac": rbac, "actions": actions})
    except Exception as exc:  # pragma: no cover - surfaced in evidence
        logger.exception("Containment failed")
        summary.update({"status": "error", "error": str(exc)})

    return summary


def ensure_rbac(endpoint: str, http: urllib3.PoolManager, token: str) -> Dict[str, bool]:
    results = {
        "serviceAccountCreated": False,
        "clusterRoleCreated": False,
        "clusterRoleBindingCreated": False,
    }

    # ServiceAccount
    sa_path = f"/api/v1/namespaces/{SERVICE_ACCOUNT_NAMESPACE}/serviceaccounts/{SERVICE_ACCOUNT_NAME}"
    if not resource_exists(endpoint, http, token, sa_path):
        body = {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": SERVICE_ACCOUNT_NAME,
                "namespace": SERVICE_ACCOUNT_NAMESPACE,
            },
        }
        if ROLE_ARN:
            body["metadata"]["annotations"] = {"eks.amazonaws.com/role-arn": ROLE_ARN}
        request(endpoint, http, token, "POST", f"/api/v1/namespaces/{SERVICE_ACCOUNT_NAMESPACE}/serviceaccounts", body)
        results["serviceAccountCreated"] = True

    # ClusterRole
    cr_path = f"/apis/rbac.authorization.k8s.io/v1/clusterroles/{CLUSTER_ROLE_NAME}"
    if not resource_exists(endpoint, http, token, cr_path):
        body = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {"name": CLUSTER_ROLE_NAME},
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["pods"],
                    "verbs": ["get", "list", "patch", "update"],
                },
                {
                    "apiGroups": ["apps"],
                    "resources": ["deployments"],
                    "verbs": ["get", "list", "patch", "update"],
                },
            ],
        }
        request(endpoint, http, token, "POST", "/apis/rbac.authorization.k8s.io/v1/clusterroles", body)
        results["clusterRoleCreated"] = True

    # ClusterRoleBinding
    crb_path = f"/apis/rbac.authorization.k8s.io/v1/clusterrolebindings/{CLUSTER_ROLE_BINDING_NAME}"
    if not resource_exists(endpoint, http, token, crb_path):
        body = {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": {"name": CLUSTER_ROLE_BINDING_NAME},
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "ClusterRole",
                "name": CLUSTER_ROLE_NAME,
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": SERVICE_ACCOUNT_NAME,
                    "namespace": SERVICE_ACCOUNT_NAMESPACE,
                }
            ],
        }
        request(endpoint, http, token, "POST", "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings", body)
        results["clusterRoleBindingCreated"] = True

    return results


def perform_containment(
    endpoint: str, http: urllib3.PoolManager, token: str, namespace: str
) -> Dict[str, Any]:
    pods_endpoint = f"/api/v1/namespaces/{namespace}/pods"
    deployments_endpoint = f"/apis/apps/v1/namespaces/{namespace}/deployments"

    pods = request(endpoint, http, token, "GET", pods_endpoint).get("items", [])
    deployments = request(endpoint, http, token, "GET", deployments_endpoint).get("items", [])

    labeled_pods: List[str] = []
    for pod in pods:
        pod_name = pod["metadata"]["name"]
        labels = pod["metadata"].get("labels") or {}
        if labels.get("containment") == "true":
            continue
        patch = {"metadata": {"labels": {"containment": "true"}}}
        request(
            endpoint,
            http,
            token,
            "PATCH",
            f"{pods_endpoint}/{pod_name}",
            body=patch,
            content_type="application/merge-patch+json",
        )
        labeled_pods.append(pod_name)

    scaled_deployments: List[Dict[str, Any]] = []
    for dep in deployments:
        dep_name = dep["metadata"]["name"]
        replicas = (dep.get("spec") or {}).get("replicas", 0)
        if replicas == 0:
            continue
        patch = {"spec": {"replicas": 0}}
        request(
            endpoint,
            http,
            token,
            "PATCH",
            f"{deployments_endpoint}/{dep_name}",
            body=patch,
            content_type="application/merge-patch+json",
        )
        scaled_deployments.append({"name": dep_name, "previousReplicas": replicas})

    return {"podsLabeled": labeled_pods, "deploymentsScaled": scaled_deployments}


def resource_exists(endpoint: str, http: urllib3.PoolManager, token: str, path: str) -> bool:
    try:
        request(endpoint, http, token, "GET", path)
        return True
    except ResourceNotFound:
        return False


def request(
    endpoint: str,
    http: urllib3.PoolManager,
    token: str,
    method: str,
    path: str,
    body: Dict[str, Any] | None = None,
    content_type: str = "application/json",
) -> Dict[str, Any]:
    url = f"{endpoint}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        headers["Content-Type"] = content_type
        data = json.dumps(body).encode("utf-8")

    logger.info("Calling Kubernetes API %s %s", method, path)
    response = http.request(method, url, body=data, headers=headers)

    if response.status == 404:
        raise ResourceNotFound(path)
    if response.status >= 400:
        raise RuntimeError(f"Kubernetes API {method} {path} failed: {response.status} {response.data}")

    if response.data:
        return json.loads(response.data)
    return {}


def write_ca_file(encoded: str) -> str:
    ca_path = "/tmp/eks-ca.crt"
    with open(ca_path, "wb") as fh:
        fh.write(base64.b64decode(encoded))
    return ca_path


def build_bearer_token(cluster_name: str) -> str:
    botocore_session = botocore.session.Session()
    botocore_session.set_config_variable("region", REGION)
    creds = botocore_session.get_credentials().get_frozen_credentials()

    url = f"https://sts.{REGION}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15"
    request = AWSRequest(method="GET", url=url)
    request.headers["x-k8s-aws-id"] = cluster_name

    SigV4Auth(creds, "sts", REGION).add_auth(request)
    signed = request.prepare()
    signed_url = signed.url

    token = base64.urlsafe_b64encode(signed_url.encode("utf-8")).decode("utf-8").rstrip("=")
    return f"k8s-aws-v1.{token}"


def dashboard_handler(event, context):
    """
    Lambda Function URL entrypoint; renders a tiny HTML view of the most recent run.
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
          <h1>Latest run</h1>
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
