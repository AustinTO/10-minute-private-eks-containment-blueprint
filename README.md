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
  
Inspired by recent discussions of *AI-assisted attack simulation and role complexity* in modern AWS environments, this blueprint translates those theoretical challenges into something you can **deploy, observe, and extend**.

---

### 🚀 Quick Start
```bash
git clone https://github.com/<YOUR_USERNAME>/eks-containment-blueprint.git
cd eks-containment-blueprint
terraform init
terraform apply
