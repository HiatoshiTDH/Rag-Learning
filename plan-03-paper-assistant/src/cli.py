"""P5 (5.1) — CLI: python -m src.cli <command>

  ask "question" [--paper ID] [--section-type method] [--no-expand]
  compare "question" ID1 ID2 [...]
  ingest                    # read data/seed_papers.txt, run the full pipeline
  watch                     # scan arXiv per data/watch_keywords.txt, ingest new papers
  list                      # indexed papers
  eval [--stage v1|hybrid|rerank|full] [--note "..."]
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="paper-assistant", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ask = sub.add_parser("ask", help="Ask across the whole corpus (the router detects papers named in the question)")
    p_ask.add_argument("question")
    p_ask.add_argument("--paper", help="Restrict to one paper (arXiv id)")
    p_ask.add_argument("--section-type", choices=["abstract", "intro", "related_work",
                                                  "method", "experiment", "result", "conclusion"])
    p_ask.add_argument("--no-expand", action="store_true", help="Disable query expansion (faster/cheaper)")

    p_cmp = sub.add_parser("compare", help="Compare 2+ papers on one question")
    p_cmp.add_argument("question")
    p_cmp.add_argument("paper_ids", nargs="+")

    sub.add_parser("ingest", help="Ingest everything in data/seed_papers.txt")
    sub.add_parser("watch", help="Scan arXiv by keyword, ingest new papers")
    sub.add_parser("list", help="List indexed papers")

    p_eval = sub.add_parser("eval", help="Measure recall on the golden set")
    p_eval.add_argument("--stage", default="full", choices=["v1", "hybrid", "rerank", "full"])
    p_eval.add_argument("--note", default="", help="Note for the EXPERIMENTS.md row")
    p_eval.add_argument("--no-log", action="store_true", help="Print only, don't write EXPERIMENTS.md")

    args = parser.parse_args()

    if args.cmd == "ingest":
        from src.ingest_all import main as ingest_main
        ingest_main()

    elif args.cmd == "watch":
        from src.watch_arxiv import main as watch_main
        watch_main()

    elif args.cmd == "list":
        from src.index import list_papers
        papers = list_papers()
        if not papers:
            print("No papers yet — run `python -m src.cli ingest` first.")
        for p in papers:
            print(f'{p["paper_id"]:>16}  ({p["year"]})  {p["title"]}')

    elif args.cmd == "ask":
        from src.answer import answer, compare_papers, format_answer, route
        from src.index import list_papers

        filters = {}
        if args.paper:
            filters["paper_id"] = args.paper
        if args.section_type:
            filters["section_type"] = args.section_type

        if not filters:  # the router only steps in when the user didn't specify
            decision = route(args.question, [p["paper_id"] for p in list_papers()])
            if decision["kind"] == "compare":
                print(compare_papers(args.question, decision["paper_ids"])["text"])
                return
            if decision["kind"] == "single":
                filters["paper_id"] = decision["paper_ids"][0]

        result = answer(args.question, filters=filters or None, expand=not args.no_expand)
        print(format_answer(result))

    elif args.cmd == "compare":
        from src.answer import compare_papers
        print(compare_papers(args.question, args.paper_ids)["text"])

    elif args.cmd == "eval":
        from src.eval import log_experiment, print_report, run_eval
        result = run_eval(stage=args.stage)
        print_report(result)
        if not args.no_log:
            log_experiment(result, note=args.note)
            print(f"\nLogged to EXPERIMENTS.md")


if __name__ == "__main__":
    main()
