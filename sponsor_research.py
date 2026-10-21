
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from tavily import TavilyClient
from ai_usage_tracker import record_usage


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

def _get_client():
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is missing from the project .env file.")
    return TavilyClient(api_key=api_key)


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication."""

    parts = urlsplit(url.strip())

    # Remove fragments and trailing slashes to reduce duplicate URLs.
    path = parts.path.rstrip("/")

    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        path,
        parts.query,
        "",
    ))


def research_sponsor_plan(
    plan: dict,
    max_queries: int = 6,
    max_results_per_query: int = 5,
) -> dict:
    """
    Run a limited number of Tavily searches from a Gemini sponsor plan.

    Returns source records with their query, category, title, URL,
    content snippet, and search score.

    Does not extract or save companies to MySQL.
    """

    if max_queries < 1:
        raise ValueError("max_queries must be at least 1.")

    if max_results_per_query < 1:
        raise ValueError("max_results_per_query must be at least 1.")

    categories = plan.get("categories")

    if not isinstance(categories, list):
        raise ValueError("The sponsor plan must contain categories.")

    client = _get_client()
    all_sources = {}
    search_log = []
    searches_run = 0

    for category in categories:
        if searches_run >= max_queries:
            break

        category_name = category.get("name", "Uncategorized")
        queries = category.get("queries", [])

        if not isinstance(queries, list):
            continue

        # One query per category in this first version.
        query = next(
            (
                item.strip()
                for item in queries
                if isinstance(item, str) and item.strip()
            ),
            None,
        )

        if not query:
            continue

        print(
            f"Searching {searches_run + 1}/{max_queries}: "
            f"{category_name}"
        )
        print(f"Query: {query}")

        try:
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=max_results_per_query,
                include_answer=False,
                include_raw_content=False,
                country="india",
                include_usage=True,
            )
            usage_payload = response.get("usage") if isinstance(response, dict) else None
            credits = usage_payload.get("credits") if isinstance(usage_payload, dict) else None
            try:
                consumed_credits = float(credits) if credits is not None else 1.0
            except (TypeError, ValueError):
                consumed_credits = 1.0
            record_usage("tavily", units=max(0, consumed_credits), operation="sponsor research search")
        except Exception as error:
            # Failed requests are tracked in the search log but not counted as
            # consumed credits; the provider's billable usage is unknown here.
            search_log.append({
                "category": category_name,
                "query": query,
                "status": "failed",
                "error": str(error),
            })
            searches_run += 1
            print(f"Search failed: {error}\n")
            continue

        searches_run += 1
        result_count = 0

                # TEMPORARY DEBUG OUTPUT: Tavily search results
        raw_results = response.get("results", [])

        print(
            f"\n[TAVILY] Results for: {query}",
            flush=True,
        )

        for result_index, item in enumerate(raw_results, start=1):
            snippet = " ".join(
                (item.get("content") or "").split()
            )

            print(
                f"\n  Result {result_index}: "
                f"{item.get('title', 'Untitled')}",
                flush=True,
            )
            print(
                f"  URL: {item.get('url', '')}",
                flush=True,
            )
            print(
                f"  Snippet: {snippet[:350]}",
                flush=True,
            )

        # Continue the original source-processing logic.
        for result in raw_results:
            url = result.get("url", "").strip()

            if not url:
                continue

            normalized = normalize_url(url)

            if normalized in all_sources:
                # Preserve all queries/categories that found the same URL.
                source = all_sources[normalized]

                if query not in source["matched_queries"]:
                    source["matched_queries"].append(query)

                if category_name not in source["categories"]:
                    source["categories"].append(category_name)

                continue

            all_sources[normalized] = {
                "title": result.get("title", ""),
                "url": url,
                "content": result.get("content", ""),
                "score": result.get("score"),
                "published_date": result.get("published_date"),
                "categories": [category_name],
                "matched_queries": [query],
            }

            result_count += 1

        search_log.append({
            "category": category_name,
            "query": query,
            "status": "success",
            "results_received": len(response.get("results", [])),
            "new_unique_sources": result_count,
            "usage": response.get("usage"),
        })

        print(f"Results received: {len(response.get('results', []))}")
        print(f"New unique sources: {result_count}\n")

    return {
        "event_name": plan.get("event_name"),
        "searches_run": searches_run,
        "unique_source_count": len(all_sources),
        "sources": list(all_sources.values()),
        "search_log": search_log,
    }


if __name__ == "__main__":
    # Convenience test: use the plan generated by sponsor_planner.py.
    plan_file = BASE_DIR / "sponsor_plan_test.json"

    if not plan_file.exists():
        raise FileNotFoundError(
            "sponsor_plan_test.json not found. "
            "Run tests/test_sponsor_planner.py first."
        )

    with plan_file.open("r", encoding="utf-8") as file:
        sponsor_plan = json.load(file)

    research = research_sponsor_plan(
        sponsor_plan,
        max_queries=6,
        max_results_per_query=5,
    )

    output_file = BASE_DIR / "research_results_test.json"

    output_file.write_text(
        json.dumps(research, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n--- Research summary ---")
    print(f"Event: {research['event_name']}")
    print(f"Searches run: {research['searches_run']}")
    print(f"Unique sources: {research['unique_source_count']}")
    print(f"Saved to: {output_file}")
