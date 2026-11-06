"""The replacement for sponsorship's 0003, which Django 6.0 cannot apply."""

import importlib

from django.db import migrations

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


def test_it_adds_what_0003_adds_and_nothing_else():
    """The end state must be 0003's, so later migrations apply unchanged:
    every field 0003 adds is added with the same definition, and the only
    extra operations are the removal and return of the two relations."""
    original_adds = {
        (op.model_name, op.name): op.field.deconstruct()[1:]
        for op in original.Migration.operations
        if isinstance(op, migrations.AddField)
    }
    replacement_adds = {
        (op.model_name, op.name): op.field.deconstruct()[1:]
        for op in replacement.Migration.operations
        if isinstance(op, migrations.AddField)
    }
    for key, definition in original_adds.items():
        assert replacement_adds[key] == definition
    assert set(replacement_adds) - set(original_adds) == {
        ("sponsorshipprofile", "additional_contacts"),
        ("sponsorshipprofile", "sponsorship_tier"),
    }
