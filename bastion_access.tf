# bastion_access.tf

# 1. Create the Access Entry (The Identity)
resource "aws_eks_access_entry" "bastion" {
  cluster_name      = module.eks.cluster_name
  principal_arn     = aws_iam_role.bastion.arn
  type              = "STANDARD"
}

# 2. Attach the Admin Policy (The Permission)
# This bypasses the need for internal K8s ClusterRoleBindings!
resource "aws_eks_access_policy_association" "bastion_admin" {
  cluster_name  = module.eks.cluster_name
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  principal_arn = aws_iam_role.bastion.arn

  access_scope {
    type = "cluster"
  }
  
  # Ensure the entry exists before attaching policy
  depends_on = [aws_eks_access_entry.bastion]
}
