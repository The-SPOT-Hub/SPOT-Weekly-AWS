# ---------- IAM Role + Policy Attachments ----------

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect = "Allow"

    principals {
      type = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "spot_weekly_lambda_role" {
  name = "spot_weekly_lambda_role"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  description = "IAM role for SPOT weekly when2meet lambda process. Grants logs write access."
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution_attach" {
  role = aws_iam_role.spot_weekly_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "spot_weekly_scheduler_role" {
  name = "spot_weekly_scheduler_role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json
  description = "Allows EventBridge Scheduler to invoke the SPOT weekly Lambda."
}

# ---------- Lambda shared layer ----------

data "archive_file" "shared_layer_weekly" {
  type = "zip"
  source_dir = "${path.module}/../layers/shared"
  output_path = "${path.module}/../build/shared_layer.zip"
}

resource "aws_lambda_layer_version" "spotWeeklyShared" {
  layer_name = "spotWeeklyShared"
  filename = data.archive_file.shared_layer_weekly.output_path
  source_code_hash = data.archive_file.shared_layer_weekly.output_base64sha256
  compatible_runtimes = ["python3.14", "python3.12", "python3.13"]
  description = "Shared layer for SPOT weekly when2meet lambda process. Includes config, slack, and w2m modules + requests package"
}

# ---------- Lambda function ----------

data "archive_file" "lambda_py" {
  type = "zip"
  source_file = "${path.module}/../handler.py"
  output_path = "${path.module}/../handler.zip"
  output_file_mode = "0666"
}

resource "aws_lambda_function" "spotWeeklyLambda" {
  filename = data.archive_file.lambda_py.output_path
  function_name = "spotWeeklyLambda"
  role = aws_iam_role.spot_weekly_lambda_role.arn
  handler = "handler.lambda_handler"
  runtime = "python3.14"

  layers = [aws_lambda_layer_version.spotWeeklyShared.arn]

  environment {
    variables = {
      SLACK_BOT_TOKEN = var.slack_bot_token
      SLACK_CHANNEL_ID = var.slack_channel_id
      SLACK_APP_ID = var.slack_app_id
    }
  }

  timeout = 300
  source_code_hash = data.archive_file.lambda_py.output_base64sha256
}

# ---------- EventBridge scheduler ----------

# Set up IAM to have permission to invoke the lambda

data "aws_iam_policy_document" "scheduler_invoke_lambda" {
  statement {
    effect = "Allow"
    actions = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.spotWeeklyLambda.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_invoke_policy" {
  name   = "spot_weekly_scheduler_invoke_policy"
  role   = aws_iam_role.spot_weekly_scheduler_role.id
  policy = data.aws_iam_policy_document.scheduler_invoke_lambda.json
}

resource "aws_scheduler_schedule" "spot_weekly_schedule" {
  name = "spot_weekly_schedule"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "cron(45 07 ? * THU *)"
  schedule_expression_timezone = "America/New_York"

  target {
    arn = aws_lambda_function.spotWeeklyLambda.arn
    role_arn = aws_iam_role.spot_weekly_scheduler_role.arn
  }
}