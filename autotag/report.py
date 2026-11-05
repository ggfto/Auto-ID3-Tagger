"""The run's report: one row per decision about a file, latest row wins."""
import csv
import os

FIELDS = ["path", "status", "source", "old_artist", "old_title", "new_artist", "new_title",
          "album", "year", "genre", "cover_art", "detail"]
# Statuses a later run processes again; everything else counts as done.
RETRY_STATUSES = {"error", "restored"}
# Statuses whose file was changed and can be restored.
CHANGED_STATUSES = {"tagged", "tagged_no_reference", "tagged_from_name"}


def report_path(state_dir):
    return os.path.join(state_dir, "report.csv")


def path_key(path):
    return os.path.normcase(os.path.abspath(path))


def is_under(path, folder):
    return path_key(path).startswith(path_key(folder).rstrip(os.sep) + os.sep)


def load(state_dir):
    """Latest row of each file, by path key."""
    rows = {}
    if os.path.exists(report_path(state_dir)):
        with open(report_path(state_dir), newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f, delimiter=";"):
                rows[path_key(row["path"])] = row
    return rows


class Report:
    def __init__(self, state_dir):
        path = report_path(state_dir)
        os.makedirs(state_dir, exist_ok=True)
        is_new = not os.path.exists(path)
        self.file = open(path, "a", newline="", encoding="utf-8-sig" if is_new else "utf-8")
        self.writer = csv.DictWriter(self.file, FIELDS, delimiter=";")
        if is_new:
            self.writer.writeheader()
            self.file.flush()

    def add(self, row):
        self.writer.writerow(row)
        self.file.flush()

    def close(self):
        self.file.close()
