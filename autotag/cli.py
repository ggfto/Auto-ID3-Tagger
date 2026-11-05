import argparse
import os

from . import review, runner

DEFAULT_STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".autotag")


def main():
    parser = argparse.ArgumentParser(description="Auto ID3 Tagger via Shazam, AcoustID & MusicBrainz")
    parser.add_argument("folder", help="path to the music folder")
    parser.add_argument("--acoustid-key", default=os.environ.get("ACOUSTID_API_KEY"),
                        help="AcoustID API key (default: the ACOUSTID_API_KEY environment variable)")
    parser.add_argument("--workers", type=int, default=4, help="files processed at the same time (default: 4)")
    parser.add_argument("--state-dir", default=DEFAULT_STATE_DIR,
                        help="where the report and the original tags are kept (default: .autotag next to this script)")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--review", action="store_true", help="decide the files waiting for review under the folder")
    action.add_argument("--restore", action="store_true",
                        help="put back the original tags of the files changed under the folder")
    args = parser.parse_args()

    if not os.path.exists(args.folder):
        parser.error(f"path '{args.folder}' not found")
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    if args.restore:
        runner.restore(args.folder, args.state_dir)
    elif args.review:
        review.run_review(args.folder, args.state_dir)
    else:
        runner.run(args.folder, args.acoustid_key, args.state_dir, args.workers)
