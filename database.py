import sqlite3
import hashlib
from datetime import datetime
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "family_tree.db")

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes database tables if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # FamilyTrees
        # FamilyTrees
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS FamilyTrees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tree_name TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        created_by INTEGER,
        tree_type TEXT DEFAULT 'family'
    )
    """)

    # Contributors
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Contributors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL,
        last_active_at TEXT NOT NULL
    )
    """)

    # TreeContributors
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TreeContributors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tree_id INTEGER NOT NULL,
        contributor_id INTEGER NOT NULL,
        joined_at TEXT NOT NULL,
        last_activity_at TEXT NOT NULL,
        FOREIGN KEY (tree_id) REFERENCES FamilyTrees(id) ON DELETE CASCADE,
        FOREIGN KEY (contributor_id) REFERENCES Contributors(id) ON DELETE CASCADE,
        UNIQUE(tree_id, contributor_id)
    )
    """)

    # Persons
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Persons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tree_id INTEGER NOT NULL,
        first_name TEXT NOT NULL,
        surname_now TEXT,
        surname_at_birth TEXT,
        gender TEXT,
        birth_date TEXT,
        deceased INTEGER DEFAULT 0,
        death_date TEXT,
        phone TEXT,
        email TEXT,
        address TEXT,
        country_of_birth TEXT,
        profession TEXT,
        biography TEXT,
        interesting_facts TEXT,
        photo_path TEXT,
        is_deleted INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (tree_id) REFERENCES FamilyTrees(id) ON DELETE CASCADE
    )
    """)

    # Relationships
        # Relationships
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tree_id INTEGER NOT NULL,
        person1_id INTEGER NOT NULL,
        person2_id INTEGER NOT NULL,
        relationship_type TEXT NOT NULL, -- 'parent-child', 'partner', 'sibling'
        relationship_status TEXT DEFAULT 'active', -- 'active', 'divorced', 'widowed'
        relationship_subtype TEXT DEFAULT 'biological', -- 'biological', 'adoptive'
        created_at TEXT NOT NULL,
        FOREIGN KEY (tree_id) REFERENCES FamilyTrees(id) ON DELETE CASCADE,
        FOREIGN KEY (person1_id) REFERENCES Persons(id) ON DELETE CASCADE,
        FOREIGN KEY (person2_id) REFERENCES Persons(id) ON DELETE CASCADE
    )
    """)

    # ChangeHistory
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ChangeHistory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tree_id INTEGER NOT NULL,
        contributor_id INTEGER NOT NULL,
        person_id INTEGER,
        action TEXT NOT NULL,
        details TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (tree_id) REFERENCES FamilyTrees(id) ON DELETE CASCADE,
        FOREIGN KEY (contributor_id) REFERENCES Contributors(id) ON DELETE CASCADE,
        FOREIGN KEY (person_id) REFERENCES Persons(id) ON DELETE SET NULL
    )
    """)
        # Ensure relationship status and subtype columns exist for existing databases (migration)
    try:
        cursor.execute("ALTER TABLE Relationships ADD COLUMN relationship_status TEXT DEFAULT 'active'")
        conn.commit()
    except sqlite3.OperationalError:
        pass # Column already exists
        
    try:
        cursor.execute("ALTER TABLE Relationships ADD COLUMN relationship_subtype TEXT DEFAULT 'biological'")
        conn.commit()
    except sqlite3.OperationalError:
        pass # Column already exists
        # Ensure tree_type column exists for existing databases (migration)
    try:
        cursor.execute("ALTER TABLE FamilyTrees ADD COLUMN tree_type TEXT DEFAULT 'family'")
        conn.commit()
    except sqlite3.OperationalError:
        pass # Column already exists

    # Ensure TreeSnapshots table exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TreeSnapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tree_id INTEGER NOT NULL,
        snapshot_index INTEGER NOT NULL,
        snapshot_data TEXT NOT NULL,
        action_description TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (tree_id) REFERENCES FamilyTrees(id) ON DELETE CASCADE
    )
    """)

    # Ensure current_snapshot_index column exists on FamilyTrees (migration)
    try:
        cursor.execute("ALTER TABLE FamilyTrees ADD COLUMN current_snapshot_index INTEGER DEFAULT NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass # Column already exists

    conn.close()

# Password Hashing
def hash_password(password: str) -> str:
    """Hashes a password using SHA-256."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

# Tree Operations
def create_tree(tree_name: str, password: str, creator_name: str, creator_email: str):
    """Creates a new family tree, registers the creator as the first contributor."""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()

    try:
        # 1. Create or get contributor
        cursor.execute("SELECT id FROM Contributors WHERE email = ?", (creator_email,))
        row = cursor.fetchone()
        if row:
            contributor_id = row["id"]
            cursor.execute("UPDATE Contributors SET last_active_at = ? WHERE id = ?", (now_str, contributor_id))
        else:
            cursor.execute(
                "INSERT INTO Contributors (name, email, created_at, last_active_at) VALUES (?, ?, ?, ?)",
                (creator_name, creator_email, now_str, now_str)
            )
            contributor_id = cursor.lastrowid

        # 2. Insert Tree
        pw_hash = hash_password(password)
        cursor.execute(
            "INSERT INTO FamilyTrees (tree_name, password_hash, created_at, created_by) VALUES (?, ?, ?, ?)",
            (tree_name, pw_hash, now_str, contributor_id)
        )
        tree_id = cursor.lastrowid

        # 3. Associate Contributor with Tree
        cursor.execute(
            "INSERT INTO TreeContributors (tree_id, contributor_id, joined_at, last_activity_at) VALUES (?, ?, ?, ?)",
            (tree_id, contributor_id, now_str, now_str)
        )

        conn.commit()
        return {"tree_id": tree_id, "contributor_id": contributor_id}
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def enter_tree(tree_name: str, password: str, contributor_name: str, contributor_email: str):
    """Verifies credentials, registers contributor, and returns details."""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()

    # 1. Verify Tree
    cursor.execute("SELECT id, password_hash FROM FamilyTrees WHERE tree_name = ?", (tree_name,))
    tree = cursor.fetchone()
    if not tree:
        conn.close()
        return None
    
    if tree["password_hash"] != hash_password(password):
        conn.close()
        return None
    
    tree_id = tree["id"]

    # 2. Upsert Contributor
    cursor.execute("SELECT id FROM Contributors WHERE email = ?", (contributor_email,))
    contrib = cursor.fetchone()
    if contrib:
        contributor_id = contrib["id"]
        cursor.execute(
            "UPDATE Contributors SET name = ?, last_active_at = ? WHERE id = ?",
            (contributor_name, now_str, contributor_id)
        )
    else:
        cursor.execute(
            "INSERT INTO Contributors (name, email, created_at, last_active_at) VALUES (?, ?, ?, ?)",
            (contributor_name, contributor_email, now_str, now_str)
        )
        contributor_id = cursor.lastrowid

    # 3. Associate with Tree (TreeContributors)
    cursor.execute(
        "INSERT OR IGNORE INTO TreeContributors (tree_id, contributor_id, joined_at, last_activity_at) VALUES (?, ?, ?, ?)",
        (tree_id, contributor_id, now_str, now_str)
    )
    cursor.execute(
        "UPDATE TreeContributors SET last_activity_at = ? WHERE tree_id = ? AND contributor_id = ?",
        (now_str, tree_id, contributor_id)
    )

    conn.commit()
    conn.close()
    return {"tree_id": tree_id, "contributor_id": contributor_id}

# Contributor Operations
def get_contributor_trees(contributor_email: str):
    """Returns all trees a contributor has joined."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ft.id, ft.tree_name, ft.created_at, 
               (SELECT COUNT(*) FROM Persons p WHERE p.tree_id = ft.id AND p.is_deleted = 0) as member_count
        FROM FamilyTrees ft
        JOIN TreeContributors tc ON ft.id = tc.tree_id
        JOIN Contributors c ON tc.contributor_id = c.id
        WHERE c.email = ?
    """, (contributor_email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Log History
def log_change(tree_id: int, contributor_id: int, person_id: int, action: str, details: str):
    """Logs an action to the ChangeHistory table."""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO ChangeHistory (tree_id, contributor_id, person_id, action, details, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (tree_id, contributor_id, person_id, action, details, now_str)
    )
    conn.commit()
    conn.close()

# Stats
def get_tree_stats(tree_id: int):
    """Fetches key statistics of the tree."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT tree_type FROM FamilyTrees WHERE id = ?", (tree_id,))
    tree_type_row = cursor.fetchone()
    tree_type = tree_type_row["tree_type"] if tree_type_row else "family"

    cursor.execute("SELECT COUNT(*) FROM Persons WHERE tree_id = ? AND is_deleted = 0", (tree_id,))
    total_members = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM TreeContributors WHERE tree_id = ?", (tree_id,))
    total_contributors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM Relationships WHERE tree_id = ?", (tree_id,))
    total_relationships = cursor.fetchone()[0]

    cursor.execute("SELECT MAX(timestamp) FROM ChangeHistory WHERE tree_id = ?", (tree_id,))
    last_updated = cursor.fetchone()[0]

    conn.close()
    return {
        "members": total_members,
        "contributors": total_contributors,
        "relationships": total_relationships,
        "last_updated": last_updated or "N/A",
        "tree_type": tree_type
    }

# Person CRUD Operations
def add_person(tree_id: int, contributor_id: int, first_name: str, surname_now: str = "", surname_at_birth: str = "",
               gender: str = "", birth_date: str = "", deceased: int = 0, death_date: str = "", phone: str = "",
               email: str = "", address: str = "", country_of_birth: str = "", profession: str = "",
               biography: str = "", interesting_facts: str = "", photo_path: str = ""):
    """Adds a person node and logs the change."""
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO Persons (
            tree_id, first_name, surname_now, surname_at_birth, gender, birth_date, deceased, death_date,
            phone, email, address, country_of_birth, profession, biography, interesting_facts, photo_path,
            is_deleted, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
    """, (
        tree_id, first_name, surname_now, surname_at_birth, gender, birth_date, deceased, death_date,
        phone, email, address, country_of_birth, profession, biography, interesting_facts, photo_path,
        now_str, now_str
    ))
    person_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Log action
    full_name = f"{first_name} {surname_now}".strip()
    log_change(tree_id, contributor_id, person_id, "Add Person", f"Added new person: {full_name}")
    return person_id

def check_edit_conflict(person_id: int, updated_at_client: str):
    """
    Checks if a conflict exists between the client's version of a person and the database version.
    """
    if not updated_at_client:
        return # Skip if not provided by client
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT updated_at FROM Persons WHERE id = ?", (person_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        db_updated_at = row["updated_at"]
        if db_updated_at != updated_at_client:
            raise ValueError("Conflict detected: This person's details were updated by another contributor. Please reload the profile details and try again.")

def update_person(tree_id: int, contributor_id: int, person_id: int, updates: dict, updated_at_client: str = None):
    """Updates a person node, compares changes, and logs a human-friendly message."""
    check_edit_conflict(person_id, updated_at_client)
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()

    # 1. Get current details to find what changed and identify the target person
    cursor.execute("""
        SELECT first_name, surname_now, gender, birth_date, deceased, death_date,
               phone, email, address, country_of_birth, profession, biography,
               interesting_facts, photo_path 
        FROM Persons WHERE id = ?
    """, (person_id,))
    row = cursor.fetchone()
    old_name = f"{row['first_name']} {row['surname_now'] or ''}".strip() if row else "someone"

    changed_fields = []
    field_labels = {
        "first_name": "First Name",
        "surname_now": "Surname",
        "surname_at_birth": "Surname at Birth",
        "gender": "Gender",
        "birth_date": "Date of Birth",
        "deceased": "Deceased Status",
        "death_date": "Date of Death",
        "profession": "Profession",
        "phone": "Contact Number",
        "email": "Email Address",
        "address": "Address",
        "photo_path": "Profile Photo"
    }

    if row:
        for field, val in updates.items():
            if field in row.keys():
                # Normalize values for clean comparison
                old_val = str(row[field]).strip() if row[field] is not None else ""
                new_val = str(val).strip() if val is not None else ""
                
                # Special normalization for deceased integer comparison
                if field == "deceased":
                    try:
                        old_val = str(int(row[field]))
                        new_val = str(int(val))
                    except (ValueError, TypeError):
                        pass

                if old_val != new_val:
                    label = field_labels.get(field, field)
                    changed_fields.append(label)

    # 2. Build and execute SQL Update
    set_clauses = []
    values = []
    for field, val in updates.items():
        set_clauses.append(f"{field} = ?")
        values.append(val)

    set_clauses.append("updated_at = ?")
    values.append(now_str)
    values.append(person_id)

    set_str = ", ".join(set_clauses)
    query = f"UPDATE Persons SET {set_str} WHERE id = ?"
    cursor.execute(query, values)
    conn.commit()
    conn.close()

    # 3. Log user-friendly details
    if changed_fields:
        details_msg = f"Updated {old_name}'s profile details ({', '.join(changed_fields)})"
    else:
        details_msg = f"Saved {old_name}'s details (no changes)"
        
    log_change(tree_id, contributor_id, person_id, "Edit Person", details_msg)

def get_person(person_id: int):
    """Fetches details for a single person."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Persons WHERE id = ? AND is_deleted = 0", (person_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_active_persons(tree_id: int):
    """Fetches all non-deleted persons for a tree."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Persons WHERE tree_id = ? AND is_deleted = 0", (tree_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def search_persons(tree_id: int, query: str):
    """Searches active persons by name, phone, or email."""
    conn = get_connection()
    cursor = conn.cursor()
    search_pattern = f"%{query}%"
    cursor.execute("""
        SELECT * FROM Persons 
        WHERE tree_id = ? AND is_deleted = 0 AND (
            first_name LIKE ? OR 
            surname_now LIKE ? OR 
            surname_at_birth LIKE ? OR 
            phone LIKE ? OR 
            email LIKE ?
        )
    """, (tree_id, search_pattern, search_pattern, search_pattern, search_pattern, search_pattern))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Tree Split Validation & Deletion
def check_if_split_occurs(tree_id: int, person_id: int) -> bool:
    """
    Checks if deleting person_id would split the active family tree graph.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM Persons WHERE tree_id = ? AND is_deleted = 0", (tree_id,))
    all_person_ids = [row["id"] for row in cursor.fetchall()]

    if len(all_person_ids) <= 2:
        conn.close()
        return False

    if person_id not in all_person_ids:
        conn.close()
        return False

    cursor.execute("""
        SELECT person1_id, person2_id 
        FROM Relationships 
        WHERE tree_id = ?
    """, (tree_id,))
    all_edges = []
    for r in cursor.fetchall():
        p1, p2 = r["person1_id"], r["person2_id"]
        if p1 in all_person_ids and p2 in all_person_ids:
            all_edges.append((p1, p2))

    conn.close()

    def get_components(nodes, edges):
        adj = {n: [] for n in nodes}
        for u, v in edges:
            if u in adj and v in adj:
                adj[u].append(v)
                adj[v].append(u)

        visited = set()
        count = 0
        for node in nodes:
            if node not in visited:
                count += 1
                queue = [node]
                visited.add(node)
                while queue:
                    curr = queue.pop(0)
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
        return count

    components_before = get_components(all_person_ids, all_edges)
    remaining_nodes = [n for n in all_person_ids if n != person_id]
    remaining_edges = [(u, v) for u, v in all_edges if u != person_id and v != person_id]
    components_after = get_components(remaining_nodes, remaining_edges)

    return components_after > components_before

def delete_person(tree_id: int, contributor_id: int, person_id: int) -> bool:
    """Performs soft delete of a person, logging it and removing their relationships."""
    if check_if_split_occurs(tree_id, person_id):
        return False

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT first_name, surname_now FROM Persons WHERE id = ?", (person_id,))
    p = cursor.fetchone()
    name = f"{p['first_name']} {p['surname_now'] or ''}".strip()

    cursor.execute("UPDATE Persons SET is_deleted = 1 WHERE id = ?", (person_id,))
    cursor.execute("DELETE FROM Relationships WHERE person1_id = ? OR person2_id = ?", (person_id, person_id))

    conn.commit()
    conn.close()

    log_change(tree_id, contributor_id, person_id, "Delete Person", f"Soft-deleted person: {name}")
    return True

# Relationship Management Operations
def validate_relationship(tree_id: int, p1_id: int, p2_id: int, rel_type: str):
    """
    Validates a relationship before creation.
    Enforces age checks and cycle checks for Standard Family Trees.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tree_type FROM FamilyTrees WHERE id = ?", (tree_id,))
    t_row = cursor.fetchone()
    tree_type = t_row["tree_type"] if t_row else "family"
    
    # Only enforce if tree_type is standard 'family'
    if tree_type == 'family':
        if rel_type == 'parent-child':
            # 1. Cycle Check: Check if child is an ancestor of parent
            if would_create_cycle(tree_id, p1_id, p2_id):
                conn.close()
                raise ValueError("This relationship would create a circular ancestry loop. A person cannot be their own ancestor or descendant.")
            
            # 2. Age Check: Parent must be >= 12 years older than child
            cursor.execute("SELECT birth_date, first_name FROM Persons WHERE id = ?", (p1_id,))
            p1_row = cursor.fetchone()
            cursor.execute("SELECT birth_date, first_name FROM Persons WHERE id = ?", (p2_id,))
            p2_row = cursor.fetchone()
            
            if p1_row and p2_row and p1_row["birth_date"] and p2_row["birth_date"]:
                age_diff = None
                try:
                    p_dob = datetime.strptime(p1_row["birth_date"], "%Y-%m-%d")
                    c_dob = datetime.strptime(p2_row["birth_date"], "%Y-%m-%d")
                    age_diff = (c_dob - p_dob).days / 365.25
                except (ValueError, TypeError):
                    pass # Skip if date parsing fails
                
                if age_diff is not None and age_diff < 12:
                    p_name = p1_row["first_name"]
                    c_name = p2_row["first_name"]
                    conn.close()
                    raise ValueError(f"Impossible age gap: Parent '{p_name}' must be at least 12 years older than child '{c_name}'.")
    conn.close()

def add_relationship(tree_id: int, p1_id: int, p2_id: int, rel_type: str, status: str = 'active', subtype: str = 'biological'):
    """Creates a relationship entry after validation."""
    validate_relationship(tree_id, p1_id, p2_id, rel_type)
    
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO Relationships (tree_id, person1_id, person2_id, relationship_type, relationship_status, relationship_subtype, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (tree_id, p1_id, p2_id, rel_type, status, subtype, now_str))
    conn.commit()
    conn.close()

def create_relationship(tree_id: int, contributor_id: int, p1_id: int, p2_id: int, rel_type: str, status: str = 'active', subtype: str = 'biological'):
    """Creates a relationship between two existing nodes."""
    validate_relationship(tree_id, p1_id, p2_id, rel_type)
    
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO Relationships (tree_id, person1_id, person2_id, relationship_type, relationship_status, relationship_subtype, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (tree_id, p1_id, p2_id, rel_type, status, subtype, now_str))
    
    # Resolve names for logs
    cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (p1_id,))
    p1_name = cursor.fetchone()["first_name"]
    cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (p2_id,))
    p2_name = cursor.fetchone()["first_name"]
    conn.commit()
    conn.close()
    
    log_change(tree_id, contributor_id, p1_id, "Link Relationship", f"Linked {p1_name} and {p2_name} as {rel_type} ({subtype})")

def update_relationship_status(tree_id: int, contributor_id: int, person1_id: int, person2_id: int, status: str):
    """Updates the status of a partner relationship."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE Relationships 
        SET relationship_status = ? 
        WHERE tree_id = ? AND relationship_type = 'partner' AND (
            (person1_id = ? AND person2_id = ?) OR (person1_id = ? AND person2_id = ?)
        )
    """, (status, tree_id, person1_id, person2_id, person2_id, person1_id))
    
    # Log details
    cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (person1_id,))
    p1_name = cursor.fetchone()["first_name"]
    cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (person2_id,))
    p2_name = cursor.fetchone()["first_name"]
    conn.commit()
    conn.close()
    
    log_change(tree_id, contributor_id, person1_id, "Relationship Status", f"Updated relationship status between {p1_name} and {p2_name} to '{status}'")

def merge_persons(tree_id: int, contributor_id: int, target_id: int, duplicate_id: int):
    """
    Merges duplicate_id into target_id:
    - Moves all relationships from duplicate_id to target_id.
    - Copies empty profile fields from duplicate_id to target_id.
    - Deletes duplicate_id.
    """
    if target_id == duplicate_id:
        raise ValueError("Cannot merge a person into themselves.")
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Fetch details of both
    cursor.execute("SELECT * FROM Persons WHERE id = ?", (target_id,))
    t_row = cursor.fetchone()
    cursor.execute("SELECT * FROM Persons WHERE id = ?", (duplicate_id,))
    d_row = cursor.fetchone()
    
    if not t_row or not d_row:
        conn.close()
        raise ValueError("Target or duplicate person not found.")
        
    t_name = f"{t_row['first_name']} {t_row['surname_now'] or ''}".strip()
    d_name = f"{d_row['first_name']} {d_row['surname_now'] or ''}".strip()
    
    # 2. Copy missing fields from duplicate to target
    fields_to_copy = ["surname_now", "surname_at_birth", "gender", "birth_date", "death_date", 
                      "phone", "email", "address", "country_of_birth", "profession", "biography", 
                      "interesting_facts", "photo_path"]
    
    updates = {}
    for f in fields_to_copy:
        if not t_row[f] and d_row[f]:
            updates[f] = d_row[f]
            
    # 3. Update relationships (move them to target_id)
    cursor.execute("SELECT person1_id, person2_id, relationship_type FROM Relationships WHERE tree_id = ?", (tree_id,))
    existing_rels = [(r["person1_id"], r["person2_id"], r["relationship_type"]) for r in cursor.fetchall()]
    
    cursor.execute("SELECT id, person1_id, person2_id, relationship_type FROM Relationships WHERE person1_id = ? OR person2_id = ?", (duplicate_id, duplicate_id))
    dup_rels = cursor.fetchall()
    
    for r in dup_rels:
        rel_id = r["id"]
        p1 = target_id if r["person1_id"] == duplicate_id else r["person1_id"]
        p2 = target_id if r["person2_id"] == duplicate_id else r["person2_id"]
        r_type = r["relationship_type"]
        
        # Check if self or duplicate
        if p1 == p2:
            cursor.execute("DELETE FROM Relationships WHERE id = ?", (rel_id,))
        elif (p1, p2, r_type) in existing_rels or (p2, p1, r_type) in existing_rels:
            cursor.execute("DELETE FROM Relationships WHERE id = ?", (rel_id,))
        else:
            cursor.execute("UPDATE Relationships SET person1_id = ?, person2_id = ? WHERE id = ?", (p1, p2, rel_id))
            
    # 4. Save updates to target
    if updates:
        set_clauses = [f"{f} = ?" for f in updates.keys()]
        values = list(updates.values())
        values.append(datetime.now().isoformat())
        values.append(target_id)
        cursor.execute(f"UPDATE Persons SET {', '.join(set_clauses)}, updated_at = ? WHERE id = ?", values)
        
    # 5. Delete duplicate person record
    cursor.execute("DELETE FROM Persons WHERE id = ?", (duplicate_id,))
    
    conn.commit()
    conn.close()
    
    log_change(tree_id, contributor_id, target_id, "Merge Persons", f"Merged duplicate profile '{d_name}' into '{t_name}'")

def delete_relationship(tree_id: int, p1_id: int, p2_id: int, rel_type: str):
    """Deletes a relationship entry."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM Relationships WHERE tree_id = ? AND person1_id = ? AND person2_id = ? AND relationship_type = ?",
        (tree_id, p1_id, p2_id, rel_type)
    )
    conn.commit()
    conn.close()

def get_relationships(tree_id: int):
    """Fetches all relationships for a tree."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Relationships WHERE tree_id = ?", (tree_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Composite Relationship additions
def add_parents(tree_id: int, contributor_id: int, child_id: int, father_name: str, mother_name: str):
    """Creates father and mother nodes, partners them, and links them as child's parents."""
    father_id = add_person(tree_id, contributor_id, father_name, gender="Male")
    mother_id = add_person(tree_id, contributor_id, mother_name, gender="Female")

    add_relationship(tree_id, father_id, mother_id, "partner")
    add_relationship(tree_id, father_id, child_id, "parent-child")
    add_relationship(tree_id, mother_id, child_id, "parent-child")

    # Resolve child name for friendly audit logs
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (child_id,))
    c_row = cursor.fetchone()
    c_name = c_row["first_name"] if c_row else "child"
    conn.close()

    log_change(tree_id, contributor_id, child_id, "Add Parents", f"Added parents {father_name} and {mother_name} for {c_name}")
    return father_id, mother_id

def add_sibling(tree_id: int, contributor_id: int, person_id: int, sibling_name: str, sibling_gender: str):
    """Creates a sibling and links them through the parents, or directly if no parents exist."""
    conn = get_connection()
    cursor = conn.cursor()

    # Resolve target person's name for friendly logs
    cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (person_id,))
    p_row = cursor.fetchone()
    p_name = p_row["first_name"] if p_row else "someone"

    cursor.execute("""
        SELECT person1_id FROM Relationships 
        WHERE person2_id = ? AND relationship_type = 'parent-child'
    """, (person_id,))
    parent_ids = [row["person1_id"] for row in cursor.fetchall()]
    conn.close()

    sibling_id = add_person(tree_id, contributor_id, sibling_name, gender=sibling_gender)

    if parent_ids:
        for pid in parent_ids:
            add_relationship(tree_id, pid, sibling_id, "parent-child")
        log_change(tree_id, contributor_id, person_id, "Add Sibling", f"Added sibling {sibling_name} for {p_name} via shared parents")
    else:
        add_relationship(tree_id, person_id, sibling_id, "sibling")
        log_change(tree_id, contributor_id, person_id, "Add Sibling", f"Added sibling {sibling_name} directly for {p_name}")

    return sibling_id

def add_partner(tree_id: int, contributor_id: int, person_id: int, partner_name: str, partner_gender: str):
    """Creates a partner and links relationship."""
    partner_id = add_person(tree_id, contributor_id, partner_name, gender=partner_gender)
    add_relationship(tree_id, person_id, partner_id, "partner")
    
    cursor = get_connection().cursor()
    cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (person_id,))
    pname = cursor.fetchone()["first_name"]
    log_change(tree_id, contributor_id, person_id, "Add Partner", f"Added partner {partner_name} for {pname}")
    return partner_id

def add_child(tree_id: int, contributor_id: int, parent1_id: int, child_name: str, child_gender: str, parent2_id: int = None):
    """Creates a child, connecting it to parent1 (and parent2 if provided)."""
    child_id = add_person(tree_id, contributor_id, child_name, gender=child_gender)
    add_relationship(tree_id, parent1_id, child_id, "parent-child")

    conn = get_connection()
    cursor = conn.cursor()
    
    # Get Parent 1 name
    cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (parent1_id,))
    p1_row = cursor.fetchone()
    p1_name = p1_row["first_name"] if p1_row else "Parent"

    if parent2_id:
        add_relationship(tree_id, parent2_id, child_id, "parent-child")
        # Get Parent 2 name
        cursor.execute("SELECT first_name FROM Persons WHERE id = ?", (parent2_id,))
        p2_row = cursor.fetchone()
        p2_name = p2_row["first_name"] if p2_row else "Parent"
        conn.close()
        
        log_change(tree_id, contributor_id, child_id, "Add Child", f"Added child {child_name} for {p1_name} and {p2_name}")
    else:
        conn.close()
        log_change(tree_id, contributor_id, child_id, "Add Child", f"Added child {child_name} for {p1_name}")

    return child_id

# Change History log retrieval
def get_change_history(tree_id: int, limit: int = 50):
    """Fetches recent change logs for a tree."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ch.*, c.name as contributor_name, c.email as contributor_email
        FROM ChangeHistory ch
        JOIN Contributors c ON ch.contributor_id = c.id
        WHERE ch.tree_id = ?
        ORDER BY ch.timestamp DESC
        LIMIT ?
    """, (tree_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Update tree settings
def update_tree_settings(tree_id: int, new_name: str, new_password: str = None, tree_type: str = 'family'):
    """Updates the family tree name, password, or type."""
    if tree_type == 'family' and has_cycle(tree_id):
        raise ValueError("Cannot switch to Standard Family Tree mode because the tree currently contains circular parent-child relationships.")

    conn = get_connection()
    cursor = conn.cursor()
    if new_password:
        h = hash_password(new_password)
        cursor.execute("UPDATE FamilyTrees SET tree_name = ?, password_hash = ?, tree_type = ? WHERE id = ?", (new_name, h, tree_type, tree_id))
    else:
        cursor.execute("UPDATE FamilyTrees SET tree_name = ?, tree_type = ? WHERE id = ?", (new_name, tree_type, tree_id))
    conn.commit()
    conn.close()

# Import / Export support
def export_tree_to_dict(tree_id: int) -> dict:
    """Exports all tree data to a clean dictionary representation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT tree_name, tree_type FROM FamilyTrees WHERE id = ?", (tree_id,))
    row = cursor.fetchone()
    tree_name = row["tree_name"]
    tree_type = row["tree_type"] if "tree_type" in row.keys() else "family"
    
    cursor.execute("SELECT * FROM Persons WHERE tree_id = ? AND is_deleted = 0", (tree_id,))
    persons = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM Relationships WHERE tree_id = ?", (tree_id,))
    relationships = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {
        "tree_name": tree_name,
        "tree_type": tree_type,
        "persons": persons,
        "relationships": relationships
    }

def import_tree_from_dict(tree_name: str, password: str, data: dict, creator_email: str, creator_name: str, tree_type: str = 'family'):
    """Imports an exported dictionary data into a new tree."""
    if tree_type == 'family' and has_cycle(None, data.get("relationships", [])):
        raise ValueError("Cannot import tree in Standard Family Tree mode because the imported data contains circular parent-child relationships.")

    res = create_tree(tree_name, password, creator_name, creator_email)
    new_tree_id = res["tree_id"]
    contrib_id = res["contributor_id"]

    conn = get_connection()
    cursor = conn.cursor()
    
    # Save the selected tree type
    cursor.execute("UPDATE FamilyTrees SET tree_type = ? WHERE id = ?", (tree_type, new_tree_id))
    
    id_map = {}
    now_str = datetime.now().isoformat()

    for p in data.get("persons", []):
        old_id = p["id"]
        cursor.execute("""
            INSERT INTO Persons (
                tree_id, first_name, surname_now, surname_at_birth, gender, birth_date, deceased, death_date,
                phone, email, address, country_of_birth, profession, biography, interesting_facts, photo_path,
                is_deleted, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (
            new_tree_id, p["first_name"], p.get("surname_now", ""), p.get("surname_at_birth", ""),
            p.get("gender", ""), p.get("birth_date", ""), p.get("deceased", 0), p.get("death_date", ""),
            p.get("phone", ""), p.get("email", ""), p.get("address", ""), p.get("country_of_birth", ""),
            p.get("profession", ""), p.get("biography", ""), p.get("interesting_facts", ""), p.get("photo_path", ""),
            now_str, now_str
        ))
        new_id = cursor.lastrowid
        id_map[old_id] = new_id

    for r in data.get("relationships", []):
        old_p1 = r["person1_id"]
        old_p2 = r["person2_id"]
        if old_p1 in id_map and old_p2 in id_map:
            cursor.execute("""
                INSERT INTO Relationships (tree_id, person1_id, person2_id, relationship_type, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (new_tree_id, id_map[old_p1], id_map[old_p2], r["relationship_type"], now_str))

    conn.commit()
    conn.close()
    log_change(new_tree_id, contrib_id, None, "Import Tree", f"Imported tree layout from JSON data for {tree_name}")
    return new_tree_id

def would_create_cycle(tree_id: int, parent_id: int, child_id: int) -> bool:
    """
    Returns True if making parent_id a parent of child_id would create an ancestry loop.
    This checks if parent_id is already a descendant of child_id.
    """
    if parent_id == child_id:
        return True # A person cannot be their own parent
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get all active parent-child relationships in the tree
    cursor.execute("""
        SELECT person1_id, person2_id 
        FROM Relationships 
        WHERE tree_id = ? AND relationship_type = 'parent-child'
    """, (tree_id,))
    
    # Build adjacency list: parent -> list of children
    adj = {}
    for r in cursor.fetchall():
        p, c = r["person1_id"], r["person2_id"]
        if p not in adj:
            adj[p] = []
        adj[p].append(c)
    conn.close()
    
    # Search if parent_id is reachable starting from child_id
    # (i.e., if child_id has parent_id as a descendant)
    queue = [child_id]
    visited = {child_id}
    
    while queue:
        curr = queue.pop(0)
        if curr == parent_id:
            return True # Path found, cycle would be created!
            
        for child in adj.get(curr, []):
            if child not in visited:
                visited.add(child)
                queue.append(child)
                
    return False

def has_cycle(tree_id: int, relationships: list = None) -> bool:
    """
    Checks if there are any circular parent-child relationships in the tree.
    If 'relationships' is provided, checks those instead of querying the database.
    """
    if relationships is None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT person1_id, person2_id 
            FROM Relationships 
            WHERE tree_id = ? AND relationship_type = 'parent-child'
        """, (tree_id,))
        relationships = [dict(row) for row in cursor.fetchall()]
        conn.close()

    # Build adjacency list: parent -> children
    adj = {}
    nodes = set()
    for r in relationships:
        if r.get("relationship_type") == "parent-child":
            p, c = r["person1_id"], r["person2_id"]
            nodes.add(p)
            nodes.add(c)
            if p not in adj:
                adj[p] = []
            adj[p].append(c)

    # DFS state tracker: 0 = unvisited, 1 = visiting, 2 = visited
    visited = {node: 0 for node in nodes}

    def dfs(u):
        visited[u] = 1 # visiting
        for v in adj.get(u, []):
            if visited.get(v, 0) == 1:
                return True # Cycle detected!
            if visited.get(v, 0) == 0:
                if dfs(v):
                    return True
        visited[u] = 2 # visited
        return False

    for node in nodes:
        if visited[node] == 0:
            if dfs(node):
                return True
    return False

# ----------------- UNDO / REDO SNAPSHOT ENGINE -----------------

def save_snapshot(tree_id: int, contributor_id: int, action_description: str):
    """Saves the current state of Persons and Relationships for the tree to the TreeSnapshots table."""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Get current snapshot index
        cursor.execute("SELECT current_snapshot_index FROM FamilyTrees WHERE id = ?", (tree_id,))
        row = cursor.fetchone()
        if not row:
            return
        
        curr_idx = row["current_snapshot_index"]
        if curr_idx is None:
            curr_idx = -1
            
        # Delete any future redo states (invalidate redo stack)
        cursor.execute("DELETE FROM TreeSnapshots WHERE tree_id = ? AND snapshot_index > ?", (tree_id, curr_idx))
        
        # Serialize current tree data (including soft-deleted persons for complete restoration)
        cursor.execute("SELECT * FROM Persons WHERE tree_id = ?", (tree_id,))
        persons = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM Relationships WHERE tree_id = ?", (tree_id,))
        relationships = [dict(r) for r in cursor.fetchall()]
        
        cursor.execute("SELECT tree_type FROM FamilyTrees WHERE id = ?", (tree_id,))
        tree_type = cursor.fetchone()["tree_type"]
        
        snapshot_data = json.dumps({
            "persons": persons,
            "relationships": relationships,
            "tree_type": tree_type
        })
        
        new_idx = curr_idx + 1
        now_str = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO TreeSnapshots (tree_id, snapshot_index, snapshot_data, action_description, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (tree_id, new_idx, snapshot_data, action_description, now_str))
        
        # Update current pointer
        cursor.execute("UPDATE FamilyTrees SET current_snapshot_index = ? WHERE id = ?", (new_idx, tree_id))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def ensure_initial_snapshot(tree_id: int, contributor_id: int = None):
    """Enforces that a tree has an initial snapshot (useful for legacy or newly entered trees)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT current_snapshot_index FROM FamilyTrees WHERE id = ?", (tree_id,))
        row = cursor.fetchone()
        if row and row["current_snapshot_index"] is None:
            # Check if snapshots already exist
            cursor.execute("SELECT COUNT(*) as cnt FROM TreeSnapshots WHERE tree_id = ?", (tree_id,))
            cnt = cursor.fetchone()["cnt"]
            if cnt == 0:
                if not contributor_id:
                    # Fallback: get the first contributor associated with this tree
                    cursor.execute("SELECT contributor_id FROM TreeContributors WHERE tree_id = ? LIMIT 1", (tree_id,))
                    contrib_row = cursor.fetchone()
                    contributor_id = contrib_row["contributor_id"] if contrib_row else 1
                conn.close()
                save_snapshot(tree_id, contributor_id, "Initial State")
                return
        conn.close()
    except Exception:
        if conn:
            conn.close()

def restore_snapshot_data(cursor, tree_id: int, data: dict):
    """Helper to wipe and restore all node/edge rows of a tree from snapshot data."""
    cursor.execute("DELETE FROM Relationships WHERE tree_id = ?", (tree_id,))
    cursor.execute("DELETE FROM Persons WHERE tree_id = ?", (tree_id,))
    
    if "tree_type" in data:
        cursor.execute("UPDATE FamilyTrees SET tree_type = ? WHERE id = ?", (data["tree_type"], tree_id))
        
    for p in data.get("persons", []):
        cursor.execute("""
            INSERT INTO Persons (
                id, tree_id, first_name, surname_now, surname_at_birth, gender, birth_date, deceased, death_date,
                phone, email, address, country_of_birth, profession, biography, interesting_facts, photo_path,
                is_deleted, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["id"], tree_id, p["first_name"], p.get("surname_now"), p.get("surname_at_birth"), p.get("gender"),
            p.get("birth_date"), p.get("deceased", 0), p.get("death_date"), p.get("phone"), p.get("email"),
            p.get("address"), p.get("country_of_birth"), p.get("profession"), p.get("biography"),
            p.get("interesting_facts"), p.get("photo_path"), p.get("is_deleted", 0), p.get("created_at"), p.get("updated_at")
        ))
        
    for r in data.get("relationships", []):
        cursor.execute("""
            INSERT INTO Relationships (
                id, tree_id, person1_id, person2_id, relationship_type, relationship_status, relationship_subtype, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["id"], tree_id, r["person1_id"], r["person2_id"], r["relationship_type"],
            r.get("relationship_status", "active"), r.get("relationship_subtype", "biological"), r["created_at"]
        ))

def undo_action(tree_id: int, contributor_id: int):
    """Reverts the tree state to the previous snapshot, updating change history logs."""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT current_snapshot_index FROM FamilyTrees WHERE id = ?", (tree_id,))
        row = cursor.fetchone()
        if not row or row["current_snapshot_index"] is None:
            raise ValueError("No undo state available.")
            
        curr_idx = row["current_snapshot_index"]
        if curr_idx <= 0:
            raise ValueError("Nothing to undo.")
            
        # Get description of the action being undone (at curr_idx)
        cursor.execute("SELECT action_description FROM TreeSnapshots WHERE tree_id = ? AND snapshot_index = ?", (tree_id, curr_idx))
        undone_snap = cursor.fetchone()
        undone_action = undone_snap["action_description"] if undone_snap else "Unknown Action"
        
        # Get target snapshot to restore (at target_idx)
        target_idx = curr_idx - 1
        cursor.execute("SELECT snapshot_data FROM TreeSnapshots WHERE tree_id = ? AND snapshot_index = ?", (tree_id, target_idx))
        snap = cursor.fetchone()
        if not snap:
            raise ValueError("Undo snapshot data not found.")
            
        data = json.loads(snap["snapshot_data"])
        restore_snapshot_data(cursor, tree_id, data)
        
        cursor.execute("UPDATE FamilyTrees SET current_snapshot_index = ? WHERE id = ?", (target_idx, tree_id))
        
        # Log undo event in ChangeHistory
        now_str = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO ChangeHistory (tree_id, contributor_id, action, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (tree_id, contributor_id, "Undo", f"Undid action: {undone_action}", now_str))
        
        conn.commit()
        return {"message": "Undo successful", "action": undone_action}
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def redo_action(tree_id: int, contributor_id: int):
    """Advances the tree state to the next snapshot (if it exists), updating change history logs."""
    import json
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT current_snapshot_index FROM FamilyTrees WHERE id = ?", (tree_id,))
        row = cursor.fetchone()
        if not row or row["current_snapshot_index"] is None:
            raise ValueError("No redo state available.")
            
        curr_idx = row["current_snapshot_index"]
        
        target_idx = curr_idx + 1
        cursor.execute("SELECT snapshot_data, action_description FROM TreeSnapshots WHERE tree_id = ? AND snapshot_index = ?", (tree_id, target_idx))
        snap = cursor.fetchone()
        if not snap:
            raise ValueError("Nothing to redo.")
            
        data = json.loads(snap["snapshot_data"])
        restore_snapshot_data(cursor, tree_id, data)
        
        cursor.execute("UPDATE FamilyTrees SET current_snapshot_index = ? WHERE id = ?", (target_idx, tree_id))
        
        # Log redo event in ChangeHistory
        now_str = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO ChangeHistory (tree_id, contributor_id, action, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (tree_id, contributor_id, "Redo", f"Redid action: {snap['action_description']}", now_str))
        
        conn.commit()
        return {"message": "Redo successful", "action": snap["action_description"]}
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_undo_redo_status(tree_id: int):
    """Returns whether undo and redo are currently available, along with their respective descriptions."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT current_snapshot_index FROM FamilyTrees WHERE id = ?", (tree_id,))
        row = cursor.fetchone()
        if not row or row["current_snapshot_index"] is None:
            return {"can_undo": False, "can_redo": False, "undo_action": None, "redo_action": None}
            
        curr_idx = row["current_snapshot_index"]
        
        # Can undo if we are past the initial state (index 0)
        can_undo = curr_idx > 0
        undo_action = None
        if can_undo:
            cursor.execute("SELECT action_description FROM TreeSnapshots WHERE tree_id = ? AND snapshot_index = ?", (tree_id, curr_idx))
            u_row = cursor.fetchone()
            if u_row:
                undo_action = u_row["action_description"]
                
        # Can redo if there exists a snapshot index curr_idx + 1
        cursor.execute("SELECT action_description FROM TreeSnapshots WHERE tree_id = ? AND snapshot_index = ?", (tree_id, curr_idx + 1))
        r_row = cursor.fetchone()
        can_redo = r_row is not None
        redo_action = r_row["action_description"] if r_row else None
        
        return {
            "can_undo": can_undo,
            "can_redo": can_redo,
            "undo_action": undo_action,
            "redo_action": redo_action
        }
    finally:
        conn.close()