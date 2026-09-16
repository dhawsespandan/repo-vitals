"""`data_source`'s second value: `backfill` becomes `corpus_scan` (Phase 11).

The name changed because the thing changed. `backfill` was a monthly
reconstruction engine — sixty as-of snapshots per repository — which was cut
along with the longitudinal study on 2026-09-09. D14 now reads "each admitted
repo is scanned once, as-of the run date", and §5.1's CHECK says
`('live_scan','corpus_scan')`.

**The `RunPython` is load-bearing, not insurance.** `AddConstraint` validates
against existing rows, so a single surviving `backfill` row would fail the
migration mid-deploy. No code ever wrote that value — the engine was never
built — so the update is expected to touch nothing, and it is here because
"expected to touch nothing" is a claim about every database this migration
will ever run against, including the teammate's, which nobody here can see.

Reversible in both directions: the reverse rewrites `corpus_scan` back before
restoring the old CHECK, for the same reason.
"""

from django.db import migrations, models

OLD_VALUE = "backfill"
NEW_VALUE = "corpus_scan"


def _rename(apps, _schema_editor, old: str, new: str) -> None:
    ScanHistory = apps.get_model("research", "ScanHistory")
    moved = ScanHistory.objects.filter(data_source=old).update(data_source=new)
    if moved:
        # Never expected. If it ever prints, someone built the backfill engine
        # after all and this migration has just relabelled its output as a
        # cross-section — which it is not.
        print(  # noqa: T201 - a migration's only channel
            f"  research.0003: relabelled {moved} '{old}' scan_history row(s) as '{new}'."
        )


def forwards(apps, schema_editor) -> None:
    _rename(apps, schema_editor, OLD_VALUE, NEW_VALUE)


def backwards(apps, schema_editor) -> None:
    _rename(apps, schema_editor, NEW_VALUE, OLD_VALUE)


class Migration(migrations.Migration):
    dependencies = [
        ("research", "0002_agentexecutiontrace"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="scanhistory",
            name="scan_history_data_source_valid",
        ),
        # Between the two constraints, so neither the old CHECK nor the new one
        # is in force while the values are moving.
        migrations.RunPython(forwards, backwards),
        migrations.AlterField(
            model_name="scanhistory",
            name="data_source",
            field=models.TextField(
                choices=[("live_scan", "Live scan"), ("corpus_scan", "Corpus scan")],
                default="live_scan",
            ),
        ),
        migrations.AddConstraint(
            model_name="scanhistory",
            constraint=models.CheckConstraint(
                condition=models.Q(("data_source__in", ["live_scan", "corpus_scan"])),
                name="scan_history_data_source_valid",
            ),
        ),
    ]
