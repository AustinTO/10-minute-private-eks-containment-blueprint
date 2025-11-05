output "configure_kubectl" {
  description = "Configure kubectl: make sure you're logged in with the correct AWS profile and run the following command to update your kubeconfig"
  value       = "aws eks --region ${local.region} update-kubeconfig --name ${module.eks.cluster_name}"
}

output "dashboard_url" {
  description = "Public URL for the minimal containment dashboard"
  value       = aws_lambda_function_url.dashboard.function_url
}
