# Accounts, historical data, and daily PDF reports

## What the report shows

The report is created from records already stored in PostgreSQL for one complete calendar day in the user's chosen time zone. It includes the reporting window and source, vehicle and station-event counts, average cycle time, first-pass yield, rework and takt misses, station-level cycle and rework detail, defect type/severity, and downtime reason and duration. It also explains that long cycles are investigation candidates rather than proof of a bottleneck. Users can download a PDF for the current or historical date range from the dashboard.

The database remains the detailed history. The PDF is a shareable snapshot of the same stored data. Metrics are calculated by the same project logic as the dashboard; missing metrics are shown as zero or no data rather than inferred. This project currently stores simulated events, not factory telemetry.

## Free hosted setup

Supabase offers a free project with a PostgreSQL database and Auth. The current Free plan lists 500 MB of database storage and 50,000 monthly active users; free projects can pause after one week without activity, so it is suitable for a portfolio demo rather than a production availability promise. Check [Supabase pricing](https://supabase.com/pricing) for current limits.

1. Create a Supabase project and leave email confirmation enabled in **Authentication → Providers → Email**.
2. In Supabase **SQL Editor**, run the complete contents of `sql/schema.sql` to create the event tables, indexes, and report-preference table. If the project already has a `report_preference` table, also run [`sql/migrations/20261123_report_preference_auth_fk.sql`](../sql/migrations/20261123_report_preference_auth_fk.sql). It changes `user_id` from text to UUID and adds a foreign key to `auth.users(id)` with `ON DELETE CASCADE`. It preserves valid existing preferences and rolls back if a preference has no matching Auth user.
3. Copy the Project URL and anon/publishable key from **Project Settings → API**. Copy a PostgreSQL connection string from **Project Settings → Database**.
4. In the Streamlit app's **Settings → Secrets**, set:

   ```toml
   SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
   SUPABASE_ANON_KEY = "YOUR_PUBLIC_ANON_KEY"
   DATABASE_URL = "postgresql://..."
   ```

   `DATABASE_URL` is private server configuration. Never use a service-role key as the anon key and never commit database credentials. The app shows the sign-in/create-account page when Supabase Auth is configured.
5. (Optional) To add Google sign-in, create a **Web application** OAuth client in Google Cloud Console. Add `https://dashboardpy-ccqdte4aobbtrah4pw3u6z.streamlit.app` and `http://localhost:8501` as authorized JavaScript origins, and add your Supabase callback URL as an authorized redirect URI: `https://uxulogbitmsewajinyvi.supabase.co/auth/v1/callback`. In Supabase **Authentication → Sign In / Providers → Google**, enable Google and enter the Google Client ID and Client Secret. In Supabase **URL Configuration → Redirect URLs**, allow the app URLs `https://dashboardpy-ccqdte4aobbtrah4pw3u6z.streamlit.app/**` and `http://localhost:8501/**` for local testing; the app adds a temporary callback parameter during OAuth. If the Google OAuth consent screen is in testing mode, add your Google account as a test user. The Google Client Secret belongs in Supabase Auth provider settings, not Streamlit secrets or GitHub.
6. Keep `API_URL` unset for the Streamlit hosted mode. With `DATABASE_URL`, the app's shared simulator writes new synthetic station, defect, and downtime events to PostgreSQL every 15 seconds. The Streamlit server runs the simulator only while the app is active; this demo does not promise continuous ingestion when nobody is viewing it.
7. To enable email delivery, add `DATABASE_URL`, `REPORT_EMAIL_FROM`, `REPORT_SMTP_HOST`, `REPORT_SMTP_USERNAME`, and `REPORT_SMTP_PASSWORD` as GitHub repository Actions secrets. Add `REPORT_SMTP_PORT` and `REPORT_SMTP_SECURITY` as Actions variables if they differ from `587` and `starttls`. The workflow checks every hour and sends a report only for accounts that opted in and whose chosen local send time has passed.
8. Sign in with a verified email/password account or Google, open **Daily PDF email (optional)**, choose a time zone and local send hour, then turn on **Email me a daily report**. The report is sent to that account's verified email. Uncheck the option and save to opt out.

If the initial Compose database was created before this feature, the simulator applies the report preference table and natural-key indexes on startup. For a managed Supabase project, running the full schema is the simplest setup.

## Local Docker setup

The default Compose stack still uses local PostgreSQL and a simulator service. It writes a persistent shared event history and exposes it through FastAPI. The dashboard's **Historical** view selects inclusive calendar dates. `assembly-line load` now appends rows and ignores duplicate station event keys rather than truncating existing facts. `docker compose down -v` deletes that local history.

Supabase Auth is optional locally. Add the project URL and anon key to `.env` to turn on the login screen. Keep `.env` private. The optional email preference can be exercised against the local Postgres database, but automated email delivery requires the GitHub Actions secrets described above.

## Privacy and limits

Passwords are handled by Supabase Auth and are not stored in the project database. Each `report_preference.user_id` is a UUID foreign key to `auth.users.id`; deleting an Auth user cascades to that user's report preference. The project stores each account's email, time zone, desired send hour, opt-in status, and last sent report date in `report_preference`. Event facts in this demo are shared simulated line data. A real multi-company product would add tenant ownership and authorization policies before storing customer event data.

PostgreSQL remains the system of record. PDFs are generated on demand or by the scheduled job; the job does not create invented events to fill an empty day. A day with no records produces an honest no-data summary.
