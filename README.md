# 10-minute-private-eks-containment-blueprint
Terraform-based AWS EKS blueprint for secure private clusters with automated containment, incident-response orchestration, and least-privilege IAM design.
# eks-containment-blueprint

**eks-containment-blueprint** is a Terraform-driven architecture built on the official [AWS EKS Blueprints](https://github.com/aws-ia/terraform-aws-eks-blueprints) pattern for fully private clusters.  
It extends that baseline into a **realistic incident-response and containment demo**, designed to showcase modern AWS IAM access patterns, Step Functions orchestration, and secure automation inside private VPC networks.

---

### 🧩 What It Does
- **Private EKS Cluster** – based on AWS’ “Fully Private Cluster” pattern (no public endpoint, no NAT).
- **Containment Automation** – EventBridge → Step Functions → Lambda workflow that can:
  - Label and quarantine namespaces.
  - Apply default-deny `NetworkPolicy` rules.
  - Scale down or annotate compromised workloads.
  - Capture before/after state to S3 for audit.
- **IAM Role Complexity** – Demonstrates advanced AWS-to-Kubernetes identity bridging using `AccessEntries` instead of legacy `aws-auth` mappings.
- **Evidence-Driven Response** – Each action produces verifiable artifacts (JSON snapshots, run records) for forensics and compliance.
- **Network Isolation Challenges** – Shows how private Lambda, EKS, and Step Functions communicate through Interface VPC Endpoints—no internet, no NAT, no compromise.
- **Phase 2 Containment** – A single Lambda function can now bootstrap its own Kubernetes RBAC and perform namespace-level containment (label pods, scale deployments) while remaining inside the private network.

---

### ⚙️ Technologies
| Layer | Tools |
|-------|--------|
| Infrastructure | Terraform, AWS EKS Blueprints |
| Orchestration | AWS Step Functions, EventBridge |
| Execution | AWS Lambda (Python, Kubernetes SDK) |
| Evidence & Audit | Amazon S3, CloudWatch Logs |
| IAM Integration | Access Entries, Fine-Grained Role Policies |

---

### 🧠 Purpose
This project demonstrates how real-world cloud security engineers handle:
- **Complex IAM Role chains**
- **Private-network constraints**
- **Automated incident containment**
- **Forensic evidence generation**
  
Inspired by recent Cloud Security Podcast titled: Incident Response of Kubernetes and how to Automate Containment with guest Damien Burks and host Ashish Rajan. The project hopes to show a workable method in a modern IaC AWS environments, this blueprint translates those theoretical challenges into something you can **deploy, observe, and extend**.

---

### 🚀 Quick Start
```bash
git clone https://github.com/AustinTO/eks-containment-blueprint.git
cd eks-containment-blueprint
terraform init
TF_LOG=ERROR terraform apply
```

---

### ✅ Current State (Phase 2 Complete)
- Private EKS cluster provisioned via Terraform with the control plane and nodes isolated inside private subnets.
- EventBridge rule, Step Functions state machine, and Lambda responder pipeline wired together — **Phase 2 adds live containment with Lambda-driven RBAC bootstrap (ServiceAccount, ClusterRole, ClusterRoleBinding) and real namespace actions (label pods, scale deployments).**
- Responder Lambda runs in private subnets, uses the EKS interface VPC endpoint, SigV4/STS token generation, and writes `audit.json` / `containment.json` evidence to S3; Dashboard Lambda stays public via a Function URL but reads the same evidence.
- Lightweight containment dashboard surfaces the latest run details (audit or containment) without extra infrastructure.
- **Operational learning:** debugging private Lambda networking, Lambda function URLs, interface VPC endpoints, and STS token generation in a fully-private cluster is now documented in this repo.

---

### 🧪 Testing Plan
1. **Provision** – Deploy with `TF_LOG=ERROR terraform apply` and wait for Terraform to finish.
2. **Trigger** – Send the demo containment event through EventBridge (matches the `demo.containment` source configured in `events.tf`):
   ```bash
   aws events put-events --entries '[
     {
       "Source": "demo.containment",
       "DetailType": "NamespaceContainmentRequested",
       "Detail": "{\"namespace\":\"default\",\"reason\":\"phase2-test\",\"mode\":\"containment\"}",
       "EventBusName": "default"
     }
   ]'
   ```
   Add `--region <aws-region>` or `--profile <name>` if needed.
3. **Verify Evidence** – Confirm a `runs/<timestamp>/containment.json` (or `audit.json`) object exists in the evidence bucket and review CloudWatch logs (look for `Calling Kubernetes API ...` lines).
4. **Check Dashboard** – Open the `dashboard_url` output in a browser to see the latest run summary (audit or containment). Dashboard runs publicly; responder stays private.
5. **Teardown (optional)** – Run `terraform destroy` when you’re finished to avoid ongoing AWS charges.

---

### 🧗 Phase 2 Challenges & Lessons Learned
- **Lambda networking inside a private VPC** – Function URLs only work when the Lambda has public egress; the dashboard had to move back out of the VPC, while the responder stayed private and required an EKS interface endpoint plus explicit `lambda:InvokeFunctionUrl` permission.
- **STS token generation** – Using `botocore.auth.SigV4Auth` directly avoided `botocore.session` API drift inside Lambda and produced the correct bearer token for the Kubernetes client.
- **Lambda packaging & redeploys** – Terraform’s `archive_file` keeps a single ZIP (`.build/responder.zip`) for both handlers; delete it (or update code) before `terraform apply` to ensure new Python changes deploy.
- **VPC Endpoints & IAM** – The responder’s IAM policy now includes `eks:GetToken` and ENI permissions; the EKS interface endpoint keeps containment traffic private without a NAT gateway.
