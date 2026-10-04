import os
import glob
import sqlite3
import re
import pandas as pd

DB_FILE = "scam_database.db"

def initialize_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Drop and recreate to guarantee clean schema
    cursor.execute("DROP TABLE IF EXISTS sebi_records")
    cursor.execute("""
        CREATE TABLE sebi_records (
            sebi_number TEXT PRIMARY KEY,
            username TEXT,
            official_entity TEXT
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_sebi_number 
        ON sebi_records(sebi_number)
    """)
    conn.commit()
    conn.close()

def process_excel_files():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    total_records = 0

    excel_files = sorted(glob.glob("project*.xls*"))
    if not excel_files:
        print("❌ No files matching 'project*.xls' or 'project*.xlsx' found.")
        conn.close()
        return

    print(f"🔍 Processing {len(excel_files)} SEBI Excel files...\n")

    # Regex pattern to match standard SEBI Registration Numbers (INZ..., INA..., INH..., INP..., IN/AIF/...)
    sebi_pattern = re.compile(r'\bIN[A-Z0-9/\-]{7,22}\b', re.IGNORECASE)

    for file_name in excel_files:
        try:
            # Read sheet without header assumptions to bypass top title banner rows
            df_raw = pd.read_excel(file_name, header=None)

            file_records = 0
            for row_idx, row in df_raw.iterrows():
                # Combine non-empty cells in current row into a single string
                row_cells = [str(v).strip() for v in row.values if pd.notna(v)]
                row_str = " ".join(row_cells)

                # Find SEBI registration matches in row
                sebi_matches = sebi_pattern.findall(row_str)
                if not sebi_matches:
                    continue

                for raw_sebi in sebi_matches:
                    sebi_no = raw_sebi.upper().strip()
                    
                    # Ignore short or generic strings that match regex by accident
                    if len(sebi_no) < 8 or sebi_no in ['INFORMATION', 'INVESTMENT']:
                        continue

                    # Identify entity name candidate from row cells (first string > 3 chars that is not the SEBI ID)
                    entity_candidates = [
                        c for c in row_cells 
                        if len(c) > 3 and sebi_no not in c.upper() and not c.isdigit() and "OCT" not in c.upper()
                    ]
                    official_entity = entity_candidates[0] if entity_candidates else "Registered Entity"

                    # Generate simplified username token for lookups (e.g., Zerodha Broking -> zerodha)
                    clean_username = re.sub(r'[^a-zA-Z0-9]', '', official_entity.split()[0]).lower() if official_entity else ""

                    cursor.execute("""
                        INSERT OR REPLACE INTO sebi_records (sebi_number, username, official_entity)
                        VALUES (?, ?, ?)
                    """, (sebi_no, clean_username, official_entity))
                    file_records += 1

            conn.commit()
            total_records += file_records
            print(f"  ✅ {file_name}: Indexed {file_records} records.")

        except Exception as e:
            print(f"  ❌ Error processing {file_name}: {e}")

    conn.close()
    print(f"\n🎉 SUCCESS: Total {total_records} SEBI records indexed into '{DB_FILE}'.")

if __name__ == "__main__":
    initialize_database()
    process_excel_files()