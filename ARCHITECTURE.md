# SPOT Weekly Automation — Serverless Architecture Document

## What it does

This workflow posts when2meet sign-up links for each Launch School course to #the-spot every Thursday morning, replacing the prior manual process of creating links and posting them individually.

This version of the system is built entirely on AWS using a serverless architecture — no servers are provisioned or managed directly.

---

## System architecture

```
EventBridge Scheduler
(cron trigger, Thursday mornings)
      │
      │ assumes spot_weekly_scheduler_role
      ▼
  Lambda Function
  (spotWeeklyLambda)
      │
      │ imports shared code from attached layer
      ▼
  Lambda Layer
  (spotWeeklyShared)
  - slack.py, w2m.py, config.py
  - requests package
      │
      ├──────────────────────┐
      │                      │
      ▼                      ▼
 when2meet.com           Slack Web API
 (link generation)       (channel posts)
```

### Why serverless

The previous version of this system ran via GitHub Actions, using a scheduled workflow on a GitHub-hosted runner. This carried two recurring issues: scheduled trigger times drifted unpredictably (sometimes by 20–40+ minutes), and GitHub Actions workflows are automatically disabled after extended periods of repository inactivity, requiring manual re-enabling.

The serverless architecture removes both issues:

- **EventBridge Scheduler** replaces the GitHub Actions cron trigger — no inactivity-based disabling, and native timezone support (the schedule is written in `America/New_York` time directly, with AWS handling DST automatically)
- **Lambda** replaces the GitHub-hosted runner — executes on a dedicated trigger with no dependency on a separate CI platform's availability
- **CloudWatch Logs** replaces GitHub Actions' run history — visible directly in AWS, giving the team a single place to check execution status without needing GitHub repository access

### Why two IAM roles

The system uses two separate IAM roles rather than one shared role:

- **`spot_weekly_lambda_role`** is assumed by the Lambda function itself, and grants only CloudWatch Logs write access for that function
- **`spot_weekly_scheduler_role`** is assumed by EventBridge Scheduler, and grants only `lambda:InvokeFunction` on this one specific Lambda

Each role is scoped to the minimum permissions its assuming service actually needs. The Lambda's own execution identity has no reason to hold invoke permissions, since it never invokes anything else; the scheduler's identity has no reason to hold logging permissions, since it doesn't run any code itself.

---

## How it works

1. Every Thursday morning, EventBridge Scheduler triggers the Lambda function on a cron schedule (timezone-aware, written in ET)
2. The Lambda checks Slack's `conversations.history` for the configured channel to determine whether a post has already been made today
3. If a post already exists for today, the Lambda exits without taking further action
4. If no post exists yet, the Lambda iterates through the configured course list
5. For each course, a when2meet event is created via a POST request to when2meet.com, and the resulting link is captured
6. A parent message is posted to Slack for the course, followed by a threaded reply containing the when2meet link
7. A short delay is applied between posts to stay within Slack's API rate limits

---

## System components

**EventBridge Schedule (`spot_weekly_schedule`)** — triggers the Lambda function on a recurring cron schedule. Configured with a specific IANA timezone (`America/New_York`) rather than UTC, so DST transitions are handled automatically.

**Lambda Function (`spotWeeklyLambda`)** — the function invoked by the schedule. The handler itself is a thin entry point that calls into the shared layer's `posts_all_courses()` function; all actual logic lives in the layer.

**Lambda Layer (`spotWeeklyShared`)** — shared code and dependencies used by the function:
- `slack.py` — Slack posting and duplicate-prevention logic
- `w2m.py` — when2meet event creation and link generation
- `config.py` — course list, message templates, and environment variable access
- `requests` package

Python Lambda layers must place importable code under a `python/` subdirectory at the root of the layer package, since only `/opt/python/` is added to the runtime's import path when the layer is attached.

**Slack Bot** — the Launch School Slack app (unchanged from the prior GitHub Actions implementation), with permission to post to #the-spot.

---

## Runtime environment

- **Lambda runtime:** Python 3.14
- **Key dependencies:**
  - `requests` — HTTP client for Slack and when2meet API calls (included via Lambda layer)

---

## Prerequisites

To set up this system from scratch you will need:

- An AWS account with access to Lambda, EventBridge Scheduler, and IAM
- Terraform installed locally
- A Slack app installed in the LS workspace with the correct scopes (see Slack app configuration below)
- Access to the LS Slack bot token, app ID, and the target channel ID

---

## Slack app configuration

**Required bot token scopes:**
- `chat:write` — post messages to channels
- `channels:history` — check whether the bot has already posted today (duplicate prevention)

No event subscriptions are required — this system only sends outbound posts on a schedule and does not listen for incoming Slack events.

---

## Course list configuration

The `courses` list in `config.py` defines which Launch School courses get a when2meet link and sign-up post each week. When Launch School adds, removes, or renames a course, this list must be updated and redeployed. The list also determines `last_course_key`, which controls which course receives the "last course" message variant instead of the standard sign-up prompt.

---

## Environment variables

| Variable | Description |
|---|---|
| `SLACK_BOT_TOKEN` | Bot OAuth token for making Slack API calls |
| `SLACK_APP_ID` | Used to identify the bot's own messages when checking for duplicate posts |
| `SLACK_CHANNEL_ID` | Channel ID of #the-spot |

---

## Infrastructure components and where to find them

| Component | AWS Console location |
|---|---|
| Lambda function | Lambda → Functions → `spotWeeklyLambda` |
| Shared layer | Lambda → Layers → `spotWeeklyShared` |
| EventBridge schedule | EventBridge → Scheduler → Schedules → `spot_weekly_schedule` |
| IAM role (Lambda) | IAM → Roles → `spot_weekly_lambda_role` |
| IAM role (Scheduler) | IAM → Roles → `spot_weekly_scheduler_role` |
| Logs | CloudWatch → Log groups → `/aws/lambda/spotWeeklyLambda` |

Infrastructure is defined as code in the `terraform/` directory of this repository.

---

## Deployment

**To deploy a code update:**
1. Update the relevant file (`handler.py`, or shared files in `layers/shared/python/`)
2. Run `terraform plan` to review the change, then `terraform apply`

Terraform detects code changes via `source_code_hash`, a hash of the deployment zip's contents attached to both the Lambda function and layer resources. This is what causes Terraform to recognize that a file has changed and redeploy it — without it, an unchanged zip *path* would look identical to Terraform even if the file contents inside it changed.

**To update environment variables:**
- Edit the corresponding value in `terraform.tfvars`, then `terraform plan` / `terraform apply`. (`terraform.tfvars` is gitignored and never committed.)

**To update the schedule:**
- Edit `schedule_expression` (and `schedule_expression_timezone`, if needed) in `main.tf`, then `terraform plan` / `terraform apply`.

---

## Monitoring and debugging

**View Lambda logs:**
- CloudWatch → Log groups → `/aws/lambda/spotWeeklyLambda` → select the most recent log stream

**Manually invoke the Lambda (without waiting for the schedule):**
- Lambda console → `spotWeeklyLambda` → **Test** tab → run a test event (the input is ignored by the handler)
- Or via CLI: `aws lambda invoke --function-name spotWeeklyLambda output.json`

Duplicate prevention applies regardless of invocation method — if the bot already posted to the configured channel today, a manual invocation will be a no-op.

**Common issues:**
- `No module named '<module>'` on invocation — the shared layer's zip does not have its contents under a `python/` subdirectory; see the Lambda Layer description under System components
- Code changes not reflected after `apply` — confirm `source_code_hash` is present on the affected resource; see Deployment
- Schedule fires on the wrong day — confirm the cron's day-of-week field uses a three-letter name (e.g. `THU`) rather than a number, since AWS's numeric day-of-week mapping differs from standard Unix cron
- IAM/permissions error immediately after first `apply` — IAM permissions can take a few seconds to propagate; re-running `terraform apply` shortly after typically resolves this

---

## Setup from scratch

1. Place `slack.py`, `w2m.py`, `config.py` under `layers/shared/python/` in this repository
2. Install dependencies into the same folder: `pip install requests -t layers/shared/python/`
3. Create `terraform/terraform.tfvars` with the Slack bot token, app ID, and target channel ID
4. `terraform init`
5. `terraform plan` to review the resources to be created
6. `terraform apply` to provision the IAM roles, Lambda layer, Lambda function, and EventBridge schedule

---

## Known limitations

- **Local Terraform state** — `terraform.tfstate` exists only on the machine that ran `apply`, with no remote backend configured. Handing this project off to another maintainer currently requires sharing the existing state file.
- **AWS account ownership** — currently hosted in a personal AWS account rather than an LS-managed one. Migration to an LS-owned account is planned but not yet scheduled.
- **No automated alerting** — failures currently require manually checking CloudWatch Logs; no CloudWatch Alarm or notification is configured for Lambda errors.
- **No CEO-side AWS access** — unlike the Slack app, where the CEO was added as a collaborator, no AWS-side access has been granted to anyone besides the original maintainer.
