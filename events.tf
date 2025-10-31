resource "aws_cloudwatch_event_rule" "containment_request" {
  name        = "${local.name}-containment-request"
  description = "Kick off containment orchestrator"
  event_pattern = jsonencode({
    "source":      ["demo.containment"],
    "detail-type": ["NamespaceContainmentRequested"]
  })
  tags = local.tags
}

resource "aws_cloudwatch_event_target" "containment_to_sfn" {
  rule      = aws_cloudwatch_event_rule.containment_request.name
  target_id = "sfn"
  arn       = aws_sfn_state_machine.containment.arn
}

resource "aws_iam_role" "events_invoke_sfn" {
  name               = "${local.name}-events-sfn-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "events.amazonaws.com" },
      Action = "sts:AssumeRole"
    }]
  })
  tags = local.tags
}

resource "aws_iam_role_policy" "events_invoke_sfn" {
  name = "${local.name}-events-invoke-sfn"
  role = aws_iam_role.events_invoke_sfn.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect   = "Allow",
      Action   = ["states:StartExecution"],
      Resource = aws_sfn_state_machine.containment.arn
    }]
  })
}

resource "aws_cloudwatch_event_target" "events_role" {
  rule      = aws_cloudwatch_event_rule.containment_request.name
  target_id = "sfn-role"
  arn       = aws_sfn_state_machine.containment.arn
  role_arn  = aws_iam_role.events_invoke_sfn.arn
}
