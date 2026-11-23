# Daily email report

The project can email a summary every day using the scheduled GitHub Actions workflow in `.github/workflows/daily-report.yml`. Each run creates a fresh synthetic sample, cleans it with the same ETL code, selects vehicles by their line-completion time in the trailing 24 hours, and emails a plain-text and HTML report. The sample is generated for the report; it is not read from a Streamlit browser session or a real factory feed.

## Configure delivery

For Gmail, I configured the SMTP host as `smtp.gmail.com`, the username and sender as the Gmail address, and port `587` with STARTTLS. The recipient and non-password SMTP settings are stored in the repository's Actions secrets/variables. Add the remaining sender credential under **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Purpose |
|---|---|
| `REPORT_SMTP_PASSWORD` | SMTP password or provider app password |

For a Gmail account, use a Google app password for SMTP authentication rather than your regular account password. If you switch providers or use implicit TLS, update the GitHub settings `REPORT_SMTP_HOST`, `REPORT_SMTP_USERNAME`, `REPORT_EMAIL_FROM`, `REPORT_SMTP_PORT`, and, when needed, `REPORT_SMTP_SECURITY=ssl`. The security mode accepts `starttls` or `ssl`. Keep the provider password in GitHub Secrets; never add it to this repository or a Streamlit secrets file.

The schedule runs once each day at **09:00 UTC**. GitHub Actions can delay scheduled runs during heavy load. The workflow can also be started manually from the repository's **Actions** tab after all secrets have been configured.

## Report contents

The report includes the time window, vehicle and station-event counts, average cycle time, first-pass yield, defect count, downtime events and minutes, bottleneck candidate, and a station-by-station cycle/rework table. All values come from the generated sample and should be described as simulated results.

## Run the report locally

After generating and cleaning data, this command writes a report JSON file without sending an email:

```bash
python -m assembly_line.report --processed data/processed --window-hours 24 --output data/processed/daily-report.json
```

To test delivery, set the same `REPORT_*` environment variables in your shell and run the command without `--output`. Do not commit those environment values.
