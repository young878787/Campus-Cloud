import psycopg2

conn = psycopg2.connect(
    host="192.168.100.125",
    port=5432,
    dbname="app",
    user="postgres",
    password="postgressql123",
)
cur = conn.cursor()

# List all tables
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema='public' 
    ORDER BY table_name
""")
print("=== ALL TABLES ===")
for r in cur.fetchall():
    print(f"  {r[0]}")

# Get columns for key tables
for table in [
    "group",
    "groupmember",
    "group_member",
    "batch_provision_job",
    "batch_provision_jobs",
    "batch_provision_task",
    "batch_provision_tasks",
    "resource",
    "user",
    "vm_request",
]:
    cur.execute(f"""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_schema='public' AND table_name='{table}'
        ORDER BY ordinal_position
    """)
    rows = cur.fetchall()
    if rows:
        print(f"\n=== TABLE: {table} ===")
        for r in rows:
            print(f"  {r[0]:30s} {r[1]:20s} nullable={r[2]:3s} default={r[3]}")

# Get foreign keys
cur.execute("""
    SELECT
        tc.table_name, kcu.column_name,
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
    ORDER BY tc.table_name
""")
print("\n=== FOREIGN KEYS ===")
for r in cur.fetchall():
    print(f"  {r[0]}.{r[1]} -> {r[2]}.{r[3]}")

conn.close()
