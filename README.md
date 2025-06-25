ReadmeFile

Conv structure:

FIRST_BUTTON, TASKNAME, DESCRIPTION,  FILEORNOT, INSERTFILE, CONFIRMATION, SEND = range(7)

database structure:

    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_chat_id TEXT NOT NULL UNIQUE,
    first_name TEXT,
    second_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    object TEXT,
    task_name TEXT,
    task_description TEXT,
    file_ids TEXT,
    claimed TEXT,
    desk TEXT,
    answ_id TEXT

