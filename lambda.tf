data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/.build/responder.zip"
}

resource "aws_lambda_function" "responder" {
  function_name = "${local.name}-responder"
  role          = aws_iam_role.lambda_exec.arn
  filename      = data.archive_file.lambda_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.lambda_zip.output_path)
  handler       = "app.handler"
  runtime       = "python3.12"
  timeout       = 180
  memory_size   = 512

  environment {
    variables = {
      EVIDENCE_BUCKET           = aws_s3_bucket.evidence.bucket
      CLUSTER_NAME              = module.eks.cluster_name
      LAMBDA_ROLE_ARN           = aws_iam_role.lambda_exec.arn
      RBAC_NAMESPACE            = "kube-system"
      RBAC_SERVICE_ACCOUNT      = "containment-lambda"
      RBAC_CLUSTER_ROLE         = "containment-lambda"
      RBAC_CLUSTER_ROLE_BINDING = "containment-lambda"
    }
  }

  vpc_config {
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.lambda.id]
  }
  tags = local.tags
}

resource "aws_lambda_function" "dashboard" {
  function_name = "${local.name}-dashboard"
  role          = aws_iam_role.lambda_exec.arn
  filename      = data.archive_file.lambda_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.lambda_zip.output_path)
  handler       = "app.dashboard_handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 128

  environment {
    variables = {
      EVIDENCE_BUCKET           = aws_s3_bucket.evidence.bucket
      CLUSTER_NAME              = module.eks.cluster_name
      LAMBDA_ROLE_ARN           = aws_iam_role.lambda_exec.arn
      RBAC_NAMESPACE            = "kube-system"
      RBAC_SERVICE_ACCOUNT      = "containment-lambda"
      RBAC_CLUSTER_ROLE         = "containment-lambda"
      RBAC_CLUSTER_ROLE_BINDING = "containment-lambda"
    }
  }

  tags = local.tags
}

resource "aws_lambda_function_url" "dashboard" {
  function_name      = aws_lambda_function.dashboard.arn
  authorization_type = "NONE"

  cors {
    allow_methods = ["GET"]
    allow_origins = ["*"]
  }
}

resource "aws_lambda_permission" "dashboard_function_url" {
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.dashboard.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
