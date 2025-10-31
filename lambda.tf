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
