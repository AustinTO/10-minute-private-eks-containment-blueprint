# Lambda execution role
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${local.name}-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = local.tags
}

# Basic permissions: CW Logs + write evidence to S3
data "aws_iam_policy_document" "lambda_policy" {
  statement {
    sid       = "Logs"
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["*"]
  }
  statement {
    sid       = "EvidenceWrite"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:AbortMultipartUpload", "s3:CreateMultipartUpload", "s3:UploadPart", "s3:CompleteMultipartUpload", "s3:GetObject"]
    resources = ["${aws_s3_bucket.evidence.arn}/*"]
  }
  statement {
    sid       = "EvidenceList"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.evidence.arn]
  }
  # DescribeCluster allows us to record cluster facts in evidence
  statement {
    sid       = "DescribeEKS"
    effect    = "Allow"
    actions   = ["eks:DescribeCluster", "eks:GetToken"]
    resources = ["*"]
  }
  statement {
    sid       = "LambdaVpcAccess"
    effect    = "Allow"
    actions   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "lambda_policy" {
  name   = "${local.name}-lambda-policy"
  policy = data.aws_iam_policy_document.lambda_policy.json
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# Step Functions role (invokes Lambda)
data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.${local.region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn_role" {
  name               = "${local.name}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "sfn_policy" {
  statement {
    sid       = "InvokeLambda"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction", "lambda:InvokeAsync"]
    resources = [aws_lambda_function.responder.arn]
  }
  statement {
    sid    = "Logs"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "sfn_policy" {
  name   = "${local.name}-sfn-policy"
  policy = data.aws_iam_policy_document.sfn_policy.json
}

resource "aws_iam_role_policy_attachment" "sfn_attach" {
  role       = aws_iam_role.sfn_role.name
  policy_arn = aws_iam_policy.sfn_policy.arn
}
