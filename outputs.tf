################################################################################
# Core Outputs
################################################################################

output "configure_kubectl" {
  description = "Command to configure kubectl for this cluster"
  value       = "aws eks --region ${local.region} update-kubeconfig --name ${module.eks.cluster_name}"
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS API endpoint"
  value       = module.eks.cluster_endpoint
}

output "evidence_bucket_name" {
  description = "S3 bucket where Lambda stores containment evidence"
  value       = aws_s3_bucket.evidence.bucket
}

output "step_function_arn" {
  description = "ARN of the Step Functions containment state machine"
  value       = aws_sfn_state_machine.containment.arn
}

output "dashboard_url" {
  description = "Public URL for the Lambda containment dashboard"
  value       = aws_lambda_function_url.dashboard.function_url
}

output "bastion_instance_id" {
  description = "Instance ID of the SSM-only bastion"
  value       = aws_instance.bastion.id
}
