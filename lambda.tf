data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/.build/responder.zip"
}

resource "aws_lambda_function" "responder" {
  function_name = "${local.name}-responder"
  role          = aws_iam_role.lambda_exec.arn
  filename      = data.archive_file.lambda_zip.output_path
  handler       = "app.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      EVIDENCE_BUCKET = aws_s3_bucket.evidence.bucket
      CLUSTER_NAME    = module.eks.cluster_name
      AWS_REGION      = local.region
    }
  }

  # NOTE: no VPC config — keeps this simple & fast to apply with your current pattern

  tags = local.tags
}

resource "aws_lambda_function" "dashboard" {
  function_name = "${local.name}-dashboard"
  role          = aws_iam_role.lambda_exec.arn
  filename      = data.archive_file.lambda_zip.output_path
  handler       = "app.dashboard_handler"
  runtime       = "python3.12"
  timeout       = 10
  memory_size   = 128

  environment {
    variables = {
      EVIDENCE_BUCKET = aws_s3_bucket.evidence.bucket
      AWS_REGION      = local.region
      CLUSTER_NAME    = module.eks.cluster_name
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
