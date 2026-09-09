"""Report serializers. camelCase, with one deliberate exception.

`fixes` is passed through exactly as stored — snake_case, §5.8's own spelling
— where every other field on this surface is camelCase like the rest of the
API. That is not an oversight. §5.8 is binding, and it is the *download*
format: "the JSON download is a machine-parseable task handoff for external
coding agents". Rewriting the keys for the browser would mean the panel showed
one shape and Phase 9's `?fmt=json` handed out another, and the two would be
free to drift. One payload, one spelling, generated once (§5.8: "one generation
produces one payload serving both downloads").
"""

from __future__ import annotations

from rest_framework import serializers

from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    """One report row, whatever state it is in.

    Polled while a generation runs, so the fields a queued row cannot have are
    null rather than absent — a client reading `status` alone knows what to
    expect, and nothing has to branch on a key's existence.
    """

    id = serializers.UUIDField(source="report_id", read_only=True)
    scanId = serializers.UUIDField(source="scan_id", read_only=True)
    dependencyId = serializers.UUIDField(source="dependency_id", read_only=True)
    type = serializers.CharField(source="report_type", read_only=True)
    summaryMd = serializers.CharField(source="summary_text", read_only=True)
    #: §5.8's array, verbatim. See the module docstring.
    fixes = serializers.JSONField(source="fixes_json", read_only=True)
    #: Which model answered — recorded per row, so a report generated before a
    #: `GROQ_MODEL` change still names the model that wrote it.
    modelName = serializers.CharField(source="model_name", read_only=True)
    errorMessage = serializers.CharField(source="error_message", read_only=True)
    generatedAt = serializers.DateTimeField(source="generated_at", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            "scanId",
            "dependencyId",
            "type",
            "status",
            "summaryMd",
            "fixes",
            "modelName",
            "errorMessage",
            "generatedAt",
            "createdAt",
        ]
        read_only_fields = fields


class ReportStateSerializer(serializers.ModelSerializer):
    """The three fields a scan's detail payload carries about its report.

    Enough to open the panel on a cached report without a second round trip,
    and small enough that the scan detail route does not become a way to fetch
    a report's whole body by accident. §5.5 gives the body its own route.
    """

    id = serializers.UUIDField(source="report_id", read_only=True)
    generatedAt = serializers.DateTimeField(source="generated_at", read_only=True)

    class Meta:
        model = Report
        fields = ["id", "status", "generatedAt"]
        read_only_fields = fields
