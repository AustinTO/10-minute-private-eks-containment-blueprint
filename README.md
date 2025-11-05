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

### ✅ Current State
- Private EKS cluster provisioned via Terraform with the control plane and nodes isolated inside private subnets.
- EventBridge rule, Step Functions state machine, and Lambda responder pipeline wired together — **Phase 1 focuses on evidence capture only (no live Kubernetes containment actions yet).**
- Evidence artifacts (JSON snapshots) persisted to S3 alongside CloudWatch logs for both Lambda functions and the state machine.
- Lightweight containment dashboard (Lambda Function URL) surfaces the latest run details without extra infrastructure.

---

### 🧪 Testing Plan
1. **Provision** – Deploy with `TF_LOG=ERROR terraform apply` and wait for Terraform to finish.
2. **Trigger** – Send the demo containment event through EventBridge (matches the `demo.containment` source configured in `events.tf`):
   ```bash
   aws events put-events --entries '[
     {
       "Source": "demo.containment",
       "DetailType": "NamespaceContainmentRequested",
       "Detail": "{\"namespace\":\"default\",\"reason\":\"phase1-test\"}",
       "EventBusName": "default"
     }
   ]'
   ```
   Add `--region <aws-region>` or `--profile <name>` if needed.
3. **Verify Evidence** – Confirm a `runs/<timestamp>/audit.json` object exists in the evidence bucket and review CloudWatch logs.
4. **Check Dashboard** – Open the `dashboard_url` output in a browser to see the latest containment summary (expect evidence only in Phase 1).
5. **Teardown (optional)** – Run `terraform destroy` when you’re finished to avoid ongoing AWS charges.
