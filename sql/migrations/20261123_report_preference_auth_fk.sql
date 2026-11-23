-- Connect existing report preferences to Supabase Auth users.
-- Run once in the Supabase SQL Editor. The transaction rolls back if any
-- existing row is not a valid UUID or has no matching Auth account.
BEGIN;

ALTER TABLE public.report_preference
    ALTER COLUMN user_id TYPE UUID USING user_id::uuid;

DO $$
BEGIN
    IF to_regclass('auth.users') IS NULL THEN
        RAISE EXCEPTION 'auth.users was not found. Run this migration in the Supabase project database';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM public.report_preference AS preference
        LEFT JOIN auth.users AS auth_user ON auth_user.id = preference.user_id
        WHERE auth_user.id IS NULL
    ) THEN
        RAISE EXCEPTION 'report_preference contains a user_id with no matching auth.users row. Resolve orphan rows before applying this migration';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.report_preference'::regclass
          AND conname = 'report_preference_user_id_fkey'
    ) THEN
        ALTER TABLE public.report_preference
            ADD CONSTRAINT report_preference_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
END $$;

COMMIT;
