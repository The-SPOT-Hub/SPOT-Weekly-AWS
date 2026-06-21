# SPOT Weekly Automation (AWS)

## What This Is

This repository contains automation that posts when2meet links to the #the-spot Slack channel every Thursday morning. It replaces the manual process of creating when2meet links and posting them to Slack.

This is the current, active version of the automation, migrated from a prior GitHub Actions–based system. See [SPOT-Automation-Weekly](https://github.com/The-SPOT-Hub/SPOT-Automation-Weekly) (archived) for the previous implementation.

**What it does:**
- Generates when2meet links for Launch School courses (see `config.py` for full list)
- Posts them to #the-spot every Thursday morning at the scheduled time
- Runs automatically via AWS EventBridge Scheduler + Lambda
- Prevents duplicate posts if the automation runs multiple times

## How It Works

### The Automation Flow

1. **Thursday morning**: EventBridge Scheduler triggers the Lambda function on a cron schedule
2. **Lambda runs**: Executes the same when2meet/Slack posting logic as the prior system
3. **Posts to Slack**: Bot posts to #the-spot channel with threaded replies
4. **Duplicate prevention**: Checks if the bot already posted today before running

### Components

```
Automation System
├── EventBridge Scheduler (cron trigger)
│   └── Invokes Lambda every Thursday
├── Lambda Function (handler.py)
│   └── Calls posts_all_courses() from the shared layer
├── Lambda Layer (shared code + dependencies)
│   ├── slack.py — posting + duplicate prevention logic
│   ├── w2m.py — when2meet link generation
│   ├── config.py — course list, message templates, credentials access
│   └── requests package
└── Slack Bot
    └── Has permission to post to #the-spot
```

### File Structure

```
spot-weekly-aws/
├── README.md
├── .gitignore
├── requirements.txt
├── handler.py (Lambda entry point)
├── layers/
│   └── shared/
│       └── python/
│           ├── slack.py
│           ├── w2m.py
│           ├── config.py
│           └── requests/ (installed via pip -t, gitignored)
└── infrastructure/
    ├── terraform.tf
    ├── variables.tf
    └── main.tf
```

Infrastructure is defined as code using Terraform. Secrets (Slack bot token, app ID, channel ID) are passed to the Lambda as environment variables, set via `terraform.tfvars` and never committed to version control.

## Why This Replaced GitHub Actions

The prior GitHub Actions–based version had recurring reliability issues — scheduled run times drifted later each week, and the workflow risked being automatically disabled after periods of repo inactivity. This version uses AWS EventBridge Scheduler for more reliable triggering and CloudWatch Logs for clearer visibility into execution history.

---

## Version History

- **v1.0** (6/21/26): Migrated from GitHub Actions to AWS
  - Created by: Karishma Tank
  - Infrastructure: Terraform (AWS Lambda, EventBridge Scheduler, IAM)
  - Slack app: Same app as the prior GitHub Actions system