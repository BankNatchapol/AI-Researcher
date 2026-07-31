"""Command-line interface for AI-Researcher."""

from datetime import date

import typer

app = typer.Typer(help="Research quantum computing and AI literature locally.")
db_app = typer.Typer(help="Manage the local PostgreSQL database.")
scope_app = typer.Typer(help="Create and inspect reproducible research scopes.")
subscribe_app = typer.Typer(help="Subscribe to a topic scope or an individual claim.")
schedule_app = typer.Typer(help="Run and inspect the daily evidence and discourse scheduler.")
app.add_typer(db_app, name="db")
app.add_typer(scope_app, name="scope")
app.add_typer(subscribe_app, name="subscribe")
app.add_typer(schedule_app, name="schedule")


@app.callback()
def main(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable DEBUG logging on stderr.",
    ),
) -> None:
    """Research quantum computing and AI literature locally."""

    from dotenv import load_dotenv

    from ai_researcher.logging import configure_logging

    # A gitignored .env in the current directory is a valid source of
    # config (see AGENTS.md) — this only fills in variables not already
    # set, so an explicit shell export always wins. Scoped to the CLI
    # entry point (not config.py's import) so it never fires just from
    # importing ai_researcher.config/cli in a test, which would otherwise
    # silently restore a variable a test intentionally deleted.
    load_dotenv()
    configure_logging(verbose=verbose)


@db_app.command("migrate")
def migrate_database() -> None:
    """Apply pending database migrations."""

    from ai_researcher.db.migrate import migrate

    applied = migrate()
    if not applied:
        typer.echo("Database already up to date.")
        return
    for migration_name in applied:
        typer.echo(f"Applied migration {migration_name}.")


@scope_app.command("new")
def new_scope(
    name: str,
    description: str | None = typer.Option(None, help="Broad research topic."),
    category: list[str] = typer.Option(
        [],
        "--category",
        "-c",
        help="arXiv category to include; repeat for multiple categories.",
    ),
    date_from: str | None = typer.Option(None, help="Earliest publication date (YYYY-MM-DD)."),
    date_to: str | None = typer.Option(None, help="Latest publication date (YYYY-MM-DD)."),
    per_source_limit: int = typer.Option(100, min=1, help="Trial result cap for each source."),
) -> None:
    """Run a narrowing dialogue and persist a new scope."""

    from ai_researcher.scoping import ScopeDefinition, dialogue, store

    broad_topic = description.strip() if description else name.replace("-", " ")
    try:
        definition = ScopeDefinition(
            name=name,
            description=broad_topic,
            include_terms=(broad_topic,),
            exclude_terms=(),
            categories=tuple(_split_values(category)),
            date_from=_parse_date(date_from, "--date-from"),
            date_to=_parse_date(date_to, "--date-to"),
            per_source_limit=per_source_limit,
        )
        narrowed = dialogue.run_dialogue(
            definition,
            confirm=lambda prompt: typer.confirm(prompt, default=False),
            emit=typer.echo,
        )
        store.save_scope(narrowed)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Saved scope '{name}'.")


@scope_app.command("show")
def show_scope(name: str) -> None:
    """Print a scope's full definition and current corpus estimate."""

    from ai_researcher.scoping import estimate, store

    definition = store.load_scope(name)
    if definition is None:
        raise typer.BadParameter(f"Unknown scope: {name}")
    estimated_size = estimate.estimate_scope(definition)
    typer.echo(f"Name: {definition.name}")
    typer.echo(f"Description: {definition.description}")
    typer.echo(f"Include terms: {_display_values(definition.include_terms)}")
    typer.echo(f"Exclude terms: {_display_values(definition.exclude_terms)}")
    typer.echo(f"arXiv categories: {_display_values(definition.categories)}")
    typer.echo(
        "Date range: "
        f"{definition.date_from.isoformat() if definition.date_from else '(any)'} to "
        f"{definition.date_to.isoformat() if definition.date_to else '(any)'}"
    )
    typer.echo(f"Per-source limit: {definition.per_source_limit}")
    typer.echo(f"Estimated corpus size: {estimated_size}")


@scope_app.command("list")
def list_scopes() -> None:
    """Print every saved scope and its current corpus estimate."""

    from ai_researcher.scoping import estimate, store

    definitions = store.list_scopes()
    if not definitions:
        typer.echo("No scopes found.")
        return
    typer.echo("Name\tEstimated corpus size")
    for definition in definitions:
        typer.echo(f"{definition.name}\t{estimate.estimate_scope(definition)}")


@app.command("ingest")
def ingest_scope(scope_name: str = typer.Argument(..., metavar="SCOPE")) -> None:
    """Run discover → acquire → parse for a saved scope."""

    from ai_researcher.ingest import pipeline

    try:
        result = pipeline.run_ingest(scope_name)
    except pipeline.UnknownScopeError as error:
        raise typer.BadParameter(str(error)) from error
    except pipeline.CorpusCeilingExceededError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error

    typer.echo(
        f"Ingest {result.state}: found {result.papers_found}, "
        f"newly parsed {result.papers_newly_parsed}."
    )


@app.command("index")
def index_scope(scope_name: str = typer.Argument(..., metavar="SCOPE")) -> None:
    """Build or refresh per-paper section trees for a saved scope."""

    from ai_researcher.trees import build

    try:
        result = build.index_scope(scope_name)
    except build.UnknownScopeError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        f"Index complete: built {result.built}, skipped {result.skipped}, failed {result.failed}."
    )


@app.command("extract")
def extract_corpus(
    scope_name: str = typer.Argument(..., metavar="SCOPE"),
    link_evidence_enabled: bool = typer.Option(
        True,
        "--link-evidence/--no-link-evidence",
        help="Link extracted claims to supporting and refuting passages.",
    ),
    dedup_enabled: bool = typer.Option(
        True,
        "--dedup/--no-dedup",
        help="Canonicalize duplicate claims after evidence linking.",
    ),
    score_enabled: bool = typer.Option(
        True,
        "--score/--no-score",
        help="Compute pipeline confidence after claim canonicalization.",
    ),
) -> None:
    """Extract claims, methods, results, datasets, and metrics for a saved scope."""

    from ai_researcher.extraction import pipeline

    try:
        result = pipeline.extract_scope(scope_name)
    except pipeline.UnknownScopeError as error:
        raise typer.BadParameter(str(error)) from error

    for paper_result in result.papers:
        if paper_result.skipped or paper_result.failed:
            continue
        typer.echo(
            f"paper {paper_result.paper_id}: "
            f"claims={paper_result.claims} methods={paper_result.methods} "
            f"results={paper_result.results} datasets={paper_result.datasets} "
            f"metrics={paper_result.metrics}"
        )
    typer.echo(
        f"Extract complete: extracted {result.extracted}, "
        f"skipped {result.skipped}, failed {result.failed}."
    )
    link_result = None
    if link_evidence_enabled:
        from ai_researcher.evidence import link as evidence_link

        link_result = evidence_link.link_scope_evidence(scope_name)
        typer.echo(
            "Evidence linking complete: "
            f"claims={link_result.claims_linked} "
            f"links={link_result.evidence_links} "
            f"failed={link_result.failed}."
        )
    if dedup_enabled:
        from ai_researcher.evidence import identity

        identity_result = identity.canonicalize_scope(scope_name)
        typer.echo(
            "Claim canonicalization complete: "
            f"pairs={identity_result.pairs_compared} "
            f"canonical={identity_result.canonical_claims} "
            f"merged={identity_result.merged_claims}."
        )
    if score_enabled and link_result is not None and link_result.failed:
        typer.echo(
            "Confidence scoring deferred: "
            f"evidence linking failed for {link_result.failed} claim(s)."
        )
    elif score_enabled:
        from ai_researcher.scoring import confidence

        confidence_result = confidence.score_scope_confidence(scope_name)
        typer.echo(
            "Confidence scoring complete: "
            f"scored={confidence_result.scored} "
            f"failed={confidence_result.failed}."
        )


claim_app = typer.Typer(help="Inspect a single extracted claim.")
app.add_typer(claim_app, name="claim")


@app.command("claims")
def list_claims_command(
    scope: str = typer.Option(..., "--scope", help="Saved scope whose claims to list."),
    claim_type: str | None = typer.Option(
        None,
        "--type",
        help="Restrict to one claim_type value.",
    ),
    min_confidence: int | None = typer.Option(
        None,
        "--min-confidence",
        min=0,
        max=100,
        help="Minimum pipeline confidence (0–100).",
    ),
    min_quality: int | None = typer.Option(
        None,
        "--min-quality",
        min=0,
        max=100,
        help="Minimum evidence quality (0–100); independent of confidence.",
    ),
) -> None:
    """List claims with confidence and evidence_quality as separate columns."""

    from ai_researcher.claims import ClaimFilters, UnknownScopeError, render_claims_table
    from ai_researcher.claims import query as claims_query

    try:
        claims = claims_query.list_claims(
            ClaimFilters(
                scope=scope,
                claim_type=claim_type,
                min_confidence=min_confidence,
                min_quality=min_quality,
            )
        )
    except UnknownScopeError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(render_claims_table(claims))


@claim_app.command("show")
def show_claim(claim_id: int = typer.Argument(..., metavar="ID")) -> None:
    """Print one claim with both scores, factors, and linked evidence."""

    from ai_researcher.claims import UnknownClaimError, render_claim_detail
    from ai_researcher.claims import query as claims_query

    try:
        claim = claims_query.get_claim(claim_id)
    except UnknownClaimError as error:
        raise typer.BadParameter(str(error)) from error
    if claim is None:
        raise typer.BadParameter(f"Unknown claim: {claim_id}")
    typer.echo(render_claim_detail(claim))


@app.command("ask")
def ask_corpus(
    question: str = typer.Argument(..., metavar="QUESTION"),
    scope: str = typer.Option(..., "--scope", help="Saved scope to search."),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Print every expanded node and the traversal stopping reason.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit one machine-readable JSON document on stdout.",
    ),
    max_nodes: int | None = typer.Option(
        None,
        "--max-nodes",
        min=1,
        help="Override the traversal node-expansion budget.",
    ),
) -> None:
    """Answer a question from grounded evidence in a saved scope."""

    from ai_researcher.answer import synthesize
    from ai_researcher.answer.render import render_answer, render_answer_json
    from ai_researcher.retrieval import traverse

    traversal_result = traverse(question, scope, max_nodes=max_nodes)
    answer = synthesize(question, traversal_result)
    output = (
        render_answer_json(answer, traversal_result.trace)
        if json_output
        else render_answer(answer, traversal_result.trace, verbose=verbose)
    )
    typer.echo(output)


@app.command("mcp")
def serve_mcp() -> None:
    """Serve the read-only research tools over MCP stdio."""

    from ai_researcher.mcp import run

    run()


@app.command("eval")
def evaluate_retrieval(
    scope: str = typer.Option(..., "--scope", help="Saved scope to evaluate."),
    k: int = typer.Option(5, "--k", min=1, help="Retrieved-node cutoff for recall@k."),
    extraction: bool = typer.Option(
        False,
        "--extraction",
        help="Score claim extraction and stance against gold claims.",
    ),
) -> None:
    """Score retrieval or extraction quality against the hand-labelled gold set."""

    from ai_researcher.eval import (
        GoldSetValidationError,
        run_evaluation,
        run_extraction_evaluation,
    )

    try:
        if extraction:
            result = run_extraction_evaluation(scope)
        else:
            result = run_evaluation(scope, k=k)
    except (FileNotFoundError, GoldSetValidationError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error

    if extraction:
        typer.echo(f"claim precision: {result.metrics.claim_precision:.3f}")
        typer.echo(f"claim recall: {result.metrics.claim_recall:.3f}")
        typer.echo(f"claim f1: {result.metrics.claim_f1:.3f}")
        typer.echo(f"evidence-span precision: {result.metrics.evidence_span_precision:.3f}")
        typer.echo(f"stance accuracy: {result.metrics.stance_accuracy:.3f}")
        typer.echo(f"report: {result.report_path}")
        return

    typer.echo(f"retrieval recall@{result.k}: {result.metrics.recall_at_k:.3f}")
    typer.echo(f"citation precision: {result.metrics.citation_precision:.3f}")
    typer.echo(f"unsupported-statement rate: {result.metrics.unsupported_statement_rate:.3f}")
    typer.echo(f"shortlist backend: {result.shortlist_backend}")
    typer.echo(f"report: {result.report_path}")


@app.command("status")
def corpus_status(
    scope: str | None = typer.Option(
        None,
        "--scope",
        help="Restrict output to one scope and list its failed papers.",
    ),
) -> None:
    """Print per-scope corpus counts (papers, parsed, abstract-only, failed, sections)."""

    from ai_researcher.corpus.status import scope_status

    statuses = scope_status(scope)
    if not statuses:
        if scope is not None:
            raise typer.BadParameter(f"Unknown scope: {scope}")
        typer.echo("No scopes found.")
        return

    for item in statuses:
        typer.echo(f"scope: {item.scope_name}")
        typer.echo(f"  papers: {item.paper_count}")
        typer.echo(f"  parsed: {item.parsed_count}")
        typer.echo(f"  abstract_only: {item.abstract_only_count}")
        typer.echo(f"  failed: {item.failed_count}")
        typer.echo(f"  sections: {item.section_count}")
        if scope is not None and item.failed_papers:
            typer.echo("  Failed papers:")
            for failed in item.failed_papers:
                typer.echo(f"    - {failed.title}: {failed.error}")


@subscribe_app.command("topic")
def subscribe_topic_command(
    scope: str = typer.Argument(..., metavar="SCOPE", help="Saved scope name to track."),
) -> None:
    """Create an active topic subscription for a scope."""

    from ai_researcher.monitor.subscription import (
        DuplicateSubscriptionError,
        UnknownScopeError,
        subscribe_topic,
    )

    try:
        record = subscribe_topic(scope)
    except (UnknownScopeError, DuplicateSubscriptionError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Subscribed #{record.id}: kind=topic target={record.target} active={record.active}")


@subscribe_app.command("claim")
def subscribe_claim_command(
    claim_id: int = typer.Argument(..., metavar="CLAIM-ID", help="Claim id to track."),
) -> None:
    """Create an active claim subscription for a canonical claim."""

    from ai_researcher.monitor.subscription import (
        DuplicateSubscriptionError,
        UnknownClaimError,
        subscribe_claim,
    )

    try:
        record = subscribe_claim(claim_id)
    except (UnknownClaimError, DuplicateSubscriptionError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Subscribed #{record.id}: kind=claim target={record.target} active={record.active}")


@app.command("subscriptions")
def list_subscriptions_command() -> None:
    """List all subscriptions with kind, target, and active state."""

    from ai_researcher.monitor.subscription import list_subscriptions

    records = list_subscriptions()
    if not records:
        typer.echo("No subscriptions.")
        return
    typer.echo("id\tkind\ttarget\tactive")
    for record in records:
        typer.echo(f"{record.id}\t{record.kind}\t{record.target}\t{record.active}")


@app.command("unsubscribe")
def unsubscribe_command(
    subscription_id: int = typer.Argument(
        ...,
        metavar="ID",
        help="Subscription id to deactivate (row is kept).",
    ),
) -> None:
    """Deactivate a subscription without deleting its history."""

    from ai_researcher.monitor.subscription import (
        UnknownSubscriptionError,
        unsubscribe,
    )

    try:
        record = unsubscribe(subscription_id)
    except UnknownSubscriptionError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        f"Unsubscribed #{record.id}: kind={record.kind} target={record.target} "
        f"active={record.active}"
    )


@app.command("sweep")
def sweep_command(
    kind: str = typer.Option(
        ...,
        "--kind",
        help="Sweep channel: evidence or discourse.",
    ),
) -> None:
    """Run a monitoring sweep for subscribed topics or discourse sources."""

    if kind == "evidence":
        from ai_researcher.monitor.sweep import run_evidence_sweep

        result = run_evidence_sweep()
    elif kind == "discourse":
        from ai_researcher.monitor.discourse_sweep import run_discourse_sweep

        result = run_discourse_sweep()
    else:
        raise typer.BadParameter("Unsupported --kind (supported: evidence, discourse)")

    typer.echo(f"Sweep kind={result.kind} state={result.state} items_found={result.items_found}")
    if result.error:
        typer.echo(f"error: {result.error}", err=True)


@app.command("digest")
def digest_command(
    since: str = typer.Option(
        ...,
        "--since",
        help="Include changes after this date (YYYY-MM-DD).",
    ),
) -> None:
    """Write a markdown digest of evidence and community attention since a date."""

    from datetime import UTC, datetime

    from ai_researcher.digest import write_digest

    try:
        since_day = _parse_date(since, "--since")
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    assert since_day is not None
    since_dt = datetime(since_day.year, since_day.month, since_day.day, tzinfo=UTC)
    markdown, _path = write_digest(since_dt)
    # Print the same content written to docs/supersaiyan/runs/digest-<date>.md
    typer.echo(markdown, nl=False)


@schedule_app.command("start")
def schedule_start_command() -> None:
    """Run APScheduler in the foreground with both daily sweeps registered."""

    from ai_researcher.monitor.scheduler import start_scheduler

    start_scheduler()


@schedule_app.command("status")
def schedule_status_command() -> None:
    """Report the next run time for each scheduled sweep job."""

    from ai_researcher.monitor.scheduler import (
        JOB_DISCOURSE,
        JOB_EVIDENCE,
        next_run_times,
    )

    times = next_run_times()
    typer.echo(f"evidence next_run={times[JOB_EVIDENCE].isoformat()}")
    typer.echo(f"discourse next_run={times[JOB_DISCOURSE].isoformat()}")


def _parse_date(value: str | None, option_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{option_name} must use YYYY-MM-DD") from error


def _split_values(values: list[str]) -> list[str]:
    return [item.strip() for value in values for item in value.split(",") if item.strip()]


def _display_values(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "(none)"
