"""Keeps the original tags of a file so they can be put back."""
import hashlib
import os
import shutil


def id3v2_size(header, file_size):
    """Total ID3v2 size given the file's first 10 bytes; 0 when there is no tag."""
    if not header.startswith(b"ID3"):
        return 0
    # Synchsafe integer conversion
    size = 10 + ((header[6] << 21) | (header[7] << 14) | (header[8] << 7) | header[9])
    if header[5] & 0x10:  # footer flag
        size += 10
    if size >= file_size:
        raise ValueError(f"invalid ID3 tag size {size} for a file of {file_size} bytes")
    return size


def _base_path(path, state_dir):
    key = hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()
    return os.path.join(state_dir, "backups", key[:2], key)


def _is_mp3(path):
    return path.lower().endswith(".mp3")


def backup_tag(path, state_dir):
    """Saves the file's tags. The first backup of a file is never replaced."""
    base = _base_path(path, state_dir)
    done_marker = base + (".v2" if _is_mp3(path) else ".full")
    if os.path.exists(done_marker):
        return
    os.makedirs(os.path.dirname(base), exist_ok=True)

    if not _is_mp3(path):
        # M4A and WMA keep tags inside the container, so the whole file is the backup.
        shutil.copyfile(path, done_marker + ".tmp")
    else:
        file_size = os.path.getsize(path)
        with open(path, "rb") as f:
            size = id3v2_size(f.read(10), file_size)
            f.seek(0)
            v2 = f.read(size)
            v1 = b""
            if file_size >= 128:
                f.seek(-128, os.SEEK_END)
                tail = f.read(128)
                if tail.startswith(b"TAG"):
                    v1 = tail
        with open(base + ".v1", "wb") as f:
            f.write(v1)
        with open(done_marker + ".tmp", "wb") as f:
            f.write(v2)
    # Renamed last: its presence marks a complete backup.
    os.replace(done_marker + ".tmp", done_marker)


def restore_tag(path, state_dir):
    base = _base_path(path, state_dir)
    if not _is_mp3(path):
        shutil.copyfile(base + ".full", path)
        return

    with open(base + ".v2", "rb") as f:
        v2 = f.read()
    with open(base + ".v1", "rb") as f:
        v1 = f.read()
    with open(path, "rb") as f:
        data = f.read()

    audio = data[id3v2_size(data[:10], len(data)):]
    if audio[-128:].startswith(b"TAG"):
        audio = audio[:-128]
    with open(path, "wb") as f:
        f.write(v2 + audio + v1)
