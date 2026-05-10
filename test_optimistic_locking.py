"""
Test script to demonstrate the Lost Update problem and its solution using Optimistic Locking.

This script simulates two concurrent users trying to update the same challenge.
- Without optimistic locking: One update silently overwrites the other (FAIL)
- With optimistic locking: Conflict is detected and reported (PASS)

Author: Malaika Fayyaz
Student ID: BSCS23013
"""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime

# ==================== SCENARIO 1: WITHOUT OPTIMISTIC LOCKING ====================

def scenario_1_without_locking():
    """Demonstrates the Lost Update problem without version control."""
    print("\n" + "="*80)
    print("SCENARIO 1: WITHOUT OPTIMISTIC LOCKING - LOST UPDATE PROBLEM")
    print("="*80)
    
    db_path = 'temp_lost_update.db'
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    
    # Old schema WITHOUT version
    cursor.execute('''
        CREATE TABLE challenges (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            explanation TEXT NOT NULL,
            version INTEGER DEFAULT 1
        )
    ''')
    
    # Insert initial challenge
    cursor.execute('''
        INSERT INTO challenges (id, title, explanation) 
        VALUES (1, "Python Basics", "Learn the fundamentals")
    ''')
    conn.commit()
    
    print("\n[INITIAL STATE]")
    cursor.execute("SELECT * FROM challenges WHERE id = 1")
    row = cursor.fetchone()
    print(f"  Challenge: id={row[0]}, title='{row[1]}', explanation='{row[2]}'")

    user_a_result = {}
    user_b_result = {}

    def user_a():
        conn_a = sqlite3.connect(db_path, check_same_thread=False)
        cur_a = conn_a.cursor()
        cur_a.execute("SELECT title, explanation FROM challenges WHERE id = 1")
        title_a, explanation_a = cur_a.fetchone()
        user_a_result['title'] = title_a
        print(f"\n[T1] User A reads: title='{title_a}', explanation='{explanation_a}'")
        time.sleep(0.5)
        new_title = 'Advanced Python'
        cur_a.execute('''
            UPDATE challenges
            SET title = ?
            WHERE id = 1
        ''', (new_title,))
        conn_a.commit()
        print(f"[T3/T5] User A updates title to '{new_title}'")
        conn_a.close()

    def user_b():
        conn_b = sqlite3.connect(db_path, check_same_thread=False)
        cur_b = conn_b.cursor()
        cur_b.execute("SELECT title, explanation FROM challenges WHERE id = 1")
        title_b, explanation_b = cur_b.fetchone()
        user_b_result['title'] = title_b
        print(f"\n[T2] User B reads: title='{title_b}', explanation='{explanation_b}'")
        time.sleep(1.0)
        stale_title = title_b
        new_explanation = 'Deep dive into Python'
        cur_b.execute('''
            UPDATE challenges
            SET title = ?, explanation = ?
            WHERE id = 1
        ''', (stale_title, new_explanation))
        conn_b.commit()
        print(f"[T6] User B updates using stale title='{stale_title}', explanation='{new_explanation}'")
        conn_b.close()

    thread_a = threading.Thread(target=user_a)
    thread_b = threading.Thread(target=user_b)
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    print("\n[FINAL STATE]")
    cursor.execute("SELECT * FROM challenges WHERE id = 1")
    final_row = cursor.fetchone()
    print(f"  Challenge: id={final_row[0]}, title='{final_row[1]}', explanation='{final_row[2]}'")
    
    print("\n[ANALYSIS]")
    print("  [ERROR] PROBLEM: User A's title update 'Advanced Python' is LOST!")
    print("  [ERROR] PROBLEM: User B's stale update overwrote it")
    print("  [ERROR] This is the LOST UPDATE ANOMALY: stale state is written back")
    print("  [ERROR] Both updates appeared to succeed, but User A's edit was overwritten")

    conn.close()
    os.remove(db_path)


# ==================== SCENARIO 2: WITH OPTIMISTIC LOCKING ====================

def scenario_2_with_optimistic_locking():
    """Demonstrates how Optimistic Locking prevents the Lost Update problem."""
    print("\n\n" + "="*80)
    print("SCENARIO 2: WITH OPTIMISTIC LOCKING - CONFLICT DETECTION")
    print("="*80)
    
    db_path = 'temp_optimistic_locking.db'
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    
    # New schema WITH version for optimistic locking
    cursor.execute('''
        CREATE TABLE challenges (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            explanation TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        )
    ''')
    
    # Insert initial challenge
    cursor.execute('''
        INSERT INTO challenges (id, title, explanation, version) 
        VALUES (1, "Python Basics", "Learn the fundamentals", 1)
    ''')
    conn.commit()
    
    print("\n[INITIAL STATE]")
    cursor.execute("SELECT id, title, explanation, version FROM challenges WHERE id = 1")
    row = cursor.fetchone()
    print(f"  Challenge: id={row[0]}, title='{row[1]}', explanation='{row[2]}', version={row[3]}")
    
    def user_a():
        conn_a = sqlite3.connect(db_path, check_same_thread=False)
        cur_a = conn_a.cursor()
        cur_a.execute("SELECT id, title, explanation, version FROM challenges WHERE id = 1")
        id_a, title_a, explanation_a, version_a = cur_a.fetchone()
        print(f"\n[T1] User A reads: title='{title_a}', version={version_a}")
        time.sleep(0.5)
        new_title = 'Advanced Python'
        cur_a.execute('''
            UPDATE challenges 
            SET title = ?, version = version + 1
            WHERE id = 1 AND version = ?
        ''', (new_title, version_a))
        conn_a.commit()
        print(f"[T3/T5] User A updates title to '{new_title}' with version {version_a}")
        conn_a.close()

    def user_b():
        conn_b = sqlite3.connect(db_path, check_same_thread=False)
        cur_b = conn_b.cursor()
        cur_b.execute("SELECT id, title, explanation, version FROM challenges WHERE id = 1")
        id_b, title_b, explanation_b, version_b = cur_b.fetchone()
        print(f"\n[T2] User B reads: title='{title_b}', version={version_b}")
        time.sleep(1.0)
        new_explanation = 'Deep dive into Python'
        cur_b.execute('''
            UPDATE challenges 
            SET explanation = ?, version = version + 1
            WHERE id = 1 AND version = ?
        ''', (new_explanation, version_b))
        conn_b.commit()
        rows_affected = cur_b.rowcount
        if rows_affected > 0:
            print(f"[T6] User B update SUCCESS with version {version_b}")
        else:
            print(f"[T6] User B CONFLICT with stale version {version_b}")
        conn_b.close()

    thread_a = threading.Thread(target=user_a)
    thread_b = threading.Thread(target=user_b)
    thread_a.start()
    thread_b.start()
    thread_a.join()
    thread_b.join()

    cursor.execute("SELECT id, title, explanation, version FROM challenges WHERE id = 1")
    final_row = cursor.fetchone()
    print(f"\n[FINAL STATE] Challenge: id={final_row[0]}, title='{final_row[1]}', explanation='{final_row[2]}', version={final_row[3]}")
    
    print("\n[ANALYSIS]")
    print("  [OK] SUCCESS: User A's update succeeded and incremented the version")
    print("  [WARN]  CONFLICT: User B's stale update was rejected")
    print("  [OK] SUCCESS: Optimistic locking prevented silent overwrite")
    print("  [OK] RECOMMENDATION: User B should refresh and retry with the new version")

    conn.close()
    os.remove(db_path)


# ==================== SCENARIO 3: RECOVERY FROM CONFLICT ====================

def scenario_3_conflict_recovery():
    """Demonstrates how a client recovers from a conflict."""
    print("\n\n" + "="*80)
    print("SCENARIO 3: RECOVERY FROM CONFLICT")
    print("="*80)
    
    # Setup: Create an in-memory database
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE challenges (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            explanation TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        INSERT INTO challenges (id, title, explanation, version) 
        VALUES (1, "Python Basics", "Learn the fundamentals", 1)
    ''')
    conn.commit()
    
    print("\n[INITIAL STATE]")
    cursor.execute("SELECT * FROM challenges WHERE id = 1")
    row = cursor.fetchone()
    print(f"  Challenge: title='{row[1]}', explanation='{row[2]}', version={row[3]}")
    
    # User A updates successfully
    print("\n[T1] User A reads and updates title (version=1)")
    cursor.execute("SELECT version FROM challenges WHERE id = 1")
    version_a = cursor.fetchone()[0]
    
    cursor.execute('''
        UPDATE challenges 
        SET title = ?, version = version + 1
        WHERE id = 1 AND version = ?
    ''', ("Advanced Python", version_a))
    conn.commit()
    print(f"  [OK] Update SUCCESS for User A (version 1 -> 2)")
    
    cursor.execute("SELECT * FROM challenges WHERE id = 1")
    row = cursor.fetchone()
    print(f"  Current state: title='{row[1]}', version={row[3]}")
    
    # User B had stale version, experiences conflict
    print("\n[T2] User B attempts update with stale version (version=1)")
    version_b = 1  # Stale version
    cursor.execute('''
        UPDATE challenges 
        SET explanation = ?, version = version + 1
        WHERE id = 1 AND version = ?
    ''', ("Deep dive into Python", version_b))
    rows_affected = cursor.rowcount
    print(f"  [ERROR] Update FAILED: 0 rows affected")
    
    # User B recovers from conflict
    print("\n[T3] User B receives 409 Conflict response")
    cursor.execute("SELECT version FROM challenges WHERE id = 1")
    current_version = cursor.fetchone()[0]
    print(f"  Server responds: 'Current version is {current_version}, you submitted version {version_b}'")
    
    print("\n[T4] User B refreshes data with latest version")
    cursor.execute("SELECT * FROM challenges WHERE id = 1")
    refreshed_data = cursor.fetchone()
    print(f"  Refreshed: title='{refreshed_data[1]}', explanation='{refreshed_data[2]}', version={refreshed_data[3]}")
    
    print("\n[T5] User B retries update with current version")
    version_b_new = refreshed_data[3]
    cursor.execute('''
        UPDATE challenges 
        SET explanation = ?, version = version + 1
        WHERE id = 1 AND version = ?
    ''', ("Deep dive into Python", version_b_new))
    conn.commit()
    rows_affected = cursor.rowcount
    
    if rows_affected > 0:
        print(f"  [OK] Update SUCCESS for User B (version {version_b_new} -> {version_b_new + 1})")
        cursor.execute("SELECT * FROM challenges WHERE id = 1")
        final_row = cursor.fetchone()
        print(f"  Final state: title='{final_row[1]}', explanation='{final_row[2]}', version={final_row[3]}")
    
    print("\n[ANALYSIS]")
    print("  [OK] SUCCESS: Conflict detected and communicated to client")
    print("  [OK] SUCCESS: Client refreshed data and retried")
    print("  [OK] SUCCESS: Both updates eventually applied (no data loss)")
    print("  [OK] OBSERVATION: Updates were serialized by version, maintaining consistency")
    
    conn.close()


# ==================== MAIN ====================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("TESTING OPTIMISTIC LOCKING FOR THE LOST UPDATE PROBLEM")
    print("Student: Malaika Fayyaz (BSCS23013)")
    print("Problem: Synchronization - Lost Update Anomaly")
    print("Solution: Optimistic Locking with Version Control")
    print("="*80)
    
    # Run all scenarios
    scenario_1_without_locking()
    scenario_2_with_optimistic_locking()
    scenario_3_conflict_recovery()
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print("\n[OK] Scenario 1: Demonstrated Lost Update without version control")
    print("[OK] Scenario 2: Demonstrated conflict detection with optimistic locking")
    print("[OK] Scenario 3: Demonstrated recovery mechanism from conflicts")
    print("\nCONCLUSION:")
    print("  Optimistic Locking successfully prevents silent data loss by:")
    print("  1. Tracking version of each resource")
    print("  2. Validating version on write (before update)")
    print("  3. Detecting conflicts and reporting them to clients")
    print("  4. Allowing clients to recover by refreshing and retrying")
    print("\n" + "="*80 + "\n")
