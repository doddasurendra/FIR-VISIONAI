import sqlite3

def migrate():
    conn = sqlite3.connect("C:/Users/LENOVO/Desktop/FIR-Sahayak/data/fir_sahayak.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cursor.fetchall()]
    if "department" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN department VARCHAR(100) DEFAULT 'AP Prohibition and Excise Department'")
        print("Added department column")
    if "approval_status" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN approval_status VARCHAR(20) DEFAULT 'APPROVED'")
        print("Added approval_status column")
    conn.commit()
    cursor.execute("PRAGMA table_info(users)")
    print("Columns now:", [c[1] for c in cursor.fetchall()])
    conn.close()

if __name__ == "__main__":
    migrate()
