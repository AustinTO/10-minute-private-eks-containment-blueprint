data "aws_caller_identity" "current" {}
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

# IAM Policy allowing the Bastion to read objects from the Evidence Bucket
data "aws_iam_policy_document" "bastion_s3_read_doc" {
  statement {
    sid       = "AllowS3ReadEvidence"
    effect    = "Allow"
    # We only need GetObject to download the kubectl binary
    actions   = ["s3:GetObject"]
    # ⚠️ This resource must include /* to cover all files in the bucket
    resources = ["${aws_s3_bucket.evidence.arn}/*"]
  }
}

resource "aws_iam_policy" "bastion_s3_read" {
  name   = "${local.name}-bastion-s3-read-policy"
  policy = data.aws_iam_policy_document.bastion_s3_read_doc.json
}

# Attach the new read policy to the Bastion's IAM Role
resource "aws_iam_role_policy_attachment" "bastion_s3_read_attach" {
  role       = aws_iam_role.bastion.name
  policy_arn = aws_iam_policy.bastion_s3_read.arn
}

# IAM Policy allowing the Bastion to read EKS cluster metadata
data "aws_iam_policy_document" "bastion_eks_read_doc" {
  statement {
    sid       = "AllowEKSDescribe"
    effect    = "Allow"
    actions   = [
      "eks:DescribeCluster",
      "eks:GetToken" # Required for generating the Kubernetes token
    ]
    # Allow reading the cluster metadata
    resources = ["arn:aws:eks:${local.region}:${data.aws_caller_identity.current.account_id}:cluster/${module.eks.cluster_name}"]
  }
}

resource "aws_iam_policy" "bastion_eks_read" {
  name   = "${local.name}-bastion-eks-read-policy"
  policy = data.aws_iam_policy_document.bastion_eks_read_doc.json
}

# Attach the new EKS read policy to the Bastion's IAM Role
resource "aws_iam_role_policy_attachment" "bastion_eks_read_attach" {
  role       = aws_iam_role.bastion.name
  policy_arn = aws_iam_policy.bastion_eks_read.arn
}