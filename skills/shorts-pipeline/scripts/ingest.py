"""Download a link-shared Google Drive file by id into a local working dir (via gdown).

The Drive MCP connector can list files but not stream large binaries into the agent; gdown
pulls them directly. Requires the containing folder to be shared "Anyone with the link".

Usage: ingest.py --file-id <ID> --out /home/user/videos/<stem>/source.mov
"""
import argparse, os, sys

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file-id", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    import gdown
    try:
        got = gdown.download(id=a.file_id, output=a.out, quiet=False)
    except Exception as e:
        got = None
        print(f"[error] {e}", file=sys.stderr)
    if not got or not os.path.exists(a.out) or os.path.getsize(a.out) < 1024:
        sys.stderr.write(
            "\n[INGEST FAILED] Could not download the file. Most likely the Drive folder is\n"
            "not link-shared. Ask the user to set the folder (or file) to\n"
            "'Anyone with the link -> Viewer', then retry. (file-id: %s)\n" % a.file_id)
        raise SystemExit(2)
    print(f"[done] {a.out} ({os.path.getsize(a.out)/1e6:.1f} MB)")

if __name__ == "__main__":
    main()
