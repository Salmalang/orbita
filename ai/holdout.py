"""Held-out zone models for the demo replay.

For each demo event, train the zone model on every OTHER event (+ background), so that replaying
that event shows genuine out-of-sample inference. Saved as registry entries
`zone_fire_holdout/<event-slug>` whose card records which event was excluded.

    .venv/Scripts/python -m ai.holdout
"""
from __future__ import annotations

import numpy as np

from ai import registry
from ai import zone_fire as Z
from ingest.loaders.fire_sensors import load_industrial_hall

# One clear fire (cable = electrical), one fire of another type, two routine nuisances.
DEMO_EVENTS = ["Cable#4", "Wood#1", "Welding#1", "Exhaust#1"]


def slug(event: str) -> str:
    return event.replace("#", "-").lower()


def build_table():
    table = Z.build_table(load_industrial_hall())
    table["event"] = table["event"].where(~table["event"].str.endswith("#-1"), "")
    return table


def train_holdouts(table=None, events=DEMO_EVENTS) -> list[dict]:
    table = build_table() if table is None else table
    cols = Z.feature_columns(table)
    zone_card = next((c for c in registry.cards() if c["name"] == "zone_fire"), None)
    cfg = zone_card["config"] if zone_card else {"p_fire": 0.95, "min_nodes": 2, "confirm_samples": Z.CONFIRM}
    cards = []
    for ev in events:
        rest = table[table["event"] != ev]
        train = Z._training_rows(rest, np.random.default_rng(0))
        model = Z.make_model().fit(train[cols], train["label"])
        cards.append(registry.save(
            "zone_fire_holdout", slug(ev), {"model": model, "features": cols, "excluded_event": ev},
            metrics={"excluded_event": ev, "training_events": int(rest.loc[rest["event"] != "", "event"].nunique())},
            config={**cfg, "excluded_event": ev}, datasets=["industrial_hall_fire"],
            description=f"Zone model trained without {ev}, used to replay {ev} out-of-sample."))
        print("saved held-out model without", ev)
    return cards


if __name__ == "__main__":
    train_holdouts()
