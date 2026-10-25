"""
Apply a SQL migration file to the application database as the role that owns the tables.

Supabase's postgres role does not own the FIR VisionAI tables (the backend's database user does),
so schema changes to those tables must run with the backend's own connection. The script reads
SUPABASE_DATABASE_URL from the given env file, refuses to run unless the connected role owns
public.documents, executes the whole file in one transaction, and prints a verification summary.
Credentials are never printed.

Usage (from backend/):
    python scripts/apply_sql_migration.py --env-file ../../.env \
        --file ../supabase/migrations/20261025120100_knowledge_base_rag_upgrade.sql
"""
import argparse
import os
import sys


def load_env(path: str) -> dict:
    values = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--env-file", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--dry-run", action="store_true", help="Run inside a transaction and roll back")
    args = p.parse_args()

    url = load_env(args.env_file).get("SUPABASE_DATABASE_URL")
    if not url:
        sys.exit("SUPABASE_DATABASE_URL is not set in the env file.")
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace("postgres://", "postgresql://")
    with open(args.file, encoding="utf-8") as f:
        sql = f.read()

    import psycopg2
    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute("select current_user, (select tableowner from pg_tables where schemaname='public' and tablename='documents')")
    user, owner = cur.fetchone()
    print(f"Connected as role '{user}'; public.documents is owned by '{owner}'.")
    if user != owner:
        conn.close()
        sys.exit("Refusing to run: the connected role does not own the application tables.")

    try:
        cur.execute(sql)
        cur.execute("select index_status, count(*) from public.documents group by 1 order by 1")
        print("documents by index_status:", cur.fetchall())
        cur.execute("""select column_name from information_schema.columns
                       where table_schema='public' and table_name='document_chunks'
                         and column_name in ('section_ref','section_title','embedding','content_tsv') order by 1""")
        print("document_chunks new columns:", [r[0] for r in cur.fetchall()])
        cur.execute("select count(*) from pg_tables where schemaname='public' and rowsecurity = false and tableowner = current_user")
        print("owned tables still without RLS:", cur.fetchone()[0])
        if args.dry_run:
            conn.rollback()
            print("Dry run: all changes rolled back.")
        else:
            conn.commit()
            print(f"Applied {os.path.basename(args.file)}.")
    except Exception as e:
        conn.rollback()
        sys.exit(f"Migration failed and was rolled back: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
