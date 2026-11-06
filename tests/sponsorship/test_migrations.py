"""The replacement for sponsorship's 0003, which Django 6.0 cannot apply."""

import importlib

from django.db import migrations
from django.db.migrations.loader import MigrationLoader
from django.test import override_settings

replacement = importlib.import_module(
    "sponsorship.migrations.0013_drop_primary_keys_without_cascade"
)
original = importlib.import_module(
    "sponsorship.migrations.0003_remove_sponsorshipprofile_application_status_and_more"
)


def _index(operations, kind, model, name):
    return next(
        i
        for i, op in enumerate(operations)
        if isinstance(op, kind) and op.model_name == model and op.name == name
    )


def test_it_replaces_0003_and_starts_from_the_same_point():
    assert replacement.Migration.replaces == [
        ("sponsorship", "0003_remove_sponsorshipprofile_application_status_and_more")
    ]
    assert replacement.Migration.dependencies == original.Migration.dependencies


def test_the_relations_leave_before_the_key_and_return_after_it():
    """Dropping ``id`` without CASCADE needs nothing pointing at it: the
    many-to-many table and the tier foreign key go first and come back once
    ``basemodel_ptr`` is the key."""
    ops = replacement.Migration.operations
    profile = "sponsorshipprofile"
    id_dropped = _index(ops, migrations.RemoveField, profile, "id")
    tier_id_dropped = _index(ops, migrations.RemoveField, "sponsorshiptier", "id")
    key_added = _index(ops, migrations.AddField, profile, "basemodel_ptr")
    tier_key_added = _index(
        ops, migrations.AddField, "sponsorshiptier", "basemodel_ptr"
    )
    for name in ("additional_contacts", "sponsorship_tier"):
        removed = _index(ops, migrations.RemoveField, profile, name)
        added = _index(ops, migrations.AddField, profile, name)
        assert removed < id_dropped < key_added < added
        assert removed < tier_id_dropped < tier_key_added < added


def test_it_leaves_the_state_0003_leaves():
    """Later migrations build on 0003's end state, so the replacement must
    arrive at the same models: the same fields with the same definitions,
    the same options and bases. Read from the graph, so a rewrite of 0003
    upstream would show here as a difference."""
    with override_settings(MIGRATION_MODULES={}):
        loader = MigrationLoader(None, replace_migrations=False)
    original_node = ("sponsorship", original.Migration.__module__.rsplit(".", 1)[1])
    replacement_node = (
        "sponsorship",
        replacement.Migration.__module__.rsplit(".", 1)[1],
    )
    after_original = loader.project_state(original_node)
    after_replacement = loader.project_state(replacement_node)
    for model in ("sponsorshipprofile", "sponsorshiptier"):
        theirs = after_original.models["sponsorship", model]
        ours = after_replacement.models["sponsorship", model]
        assert {name: f.deconstruct()[1:] for name, f in ours.fields.items()} == {
            name: f.deconstruct()[1:] for name, f in theirs.fields.items()
        }
        assert ours.options == theirs.options
        assert ours.bases == theirs.bases
