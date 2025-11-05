resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/states/${local.name}-containment"
  retention_in_days = 14
  tags              = local.tags
}

locals {
  sfn_definition = jsonencode({
    Comment = "Containment audit-orchestrator (minimal demo)"
    StartAt = "RunResponder"
    States = {
      RunResponder = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.responder.arn
          Payload = {
            "detail.$" = "$.detail"
            "mode"     = "audit"
          }
        }
        OutputPath = "$.Payload"
        End        = true
      }
    }
  })
}

resource "aws_sfn_state_machine" "containment" {
  name       = "${local.name}-containment"
  role_arn   = aws_iam_role.sfn_role.arn
  definition = local.sfn_definition

  logging_configuration {
    include_execution_data = true
    level                  = "ALL"
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
  }

  tags = local.tags
}
