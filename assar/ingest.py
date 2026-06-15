"""Convenience entrypoint: `python -m assar.ingest` -> build corpus (if needed) + ingest."""
from .rag.build_corpus import CORPUS_PATH, build_corpus
from .rag.ingest import ingest


def main():
    if not CORPUS_PATH.exists():
        print("Corpus not found — extracting prose from the PDF first ...")
        build_corpus()
    ingest()


if __name__ == "__main__":
    main()
