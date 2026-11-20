"""What an upload would send back to "needs another look", worked out before it is made.

The upload is run for real, on a copy of the workspace file that is thrown away, and the definitions that were confirmed before and need another look after are
listed, each with the reason the checks gave. So the list is what the upload then does, not a guess from what reads the dataset. Nothing of the real workspace is
written. The cost is a copy of the file for each preview, which is what a local workspace of this size can afford; a person who uploads a new dataset (nothing
reads it yet) is not asked. The board cards it moves are worked out on the same copy, before and after (change_preview).
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

from ontology_poc_generator.change_preview import upload_impact
from ontology_poc_generator.object_types import element_row
from ontology_poc_generator.review_queue import _item
from ontology_poc_generator.workspace_datasets import upload
from ontology_poc_generator.workspace_store import open_workspace


def moved_by_upload(db_path, parts: list, who: str | None, user: dict | None) -> dict:
    """{'moved': [{'element', 'kind', 'title', 'reason'}], 'datasets': [names the upload writes], 'boards': the board cards it moves (change_preview.impact's
    answer, "now" being before the upload)}: the definitions this person may see that the upload sends back. Raises what the upload itself raises when it would be
    refused (UploadRefused, ValueError)."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / 'workspace.sqlite'
        source, target = sqlite3.connect(str(db_path)), sqlite3.connect(str(copy))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        conn = open_workspace(copy)
        try:
            confirmed = [e for (e,) in conn.execute("SELECT element_id FROM element_state WHERE state = 'confirmed' ORDER BY element_id")]
            written, boards = upload_impact(conn, user, lambda: upload(conn, parts, who, user))
            moved = []
            for element_id in confirmed:
                row = element_row(conn, element_id)
                item = _item(conn, row, user, light=True) if row is not None and row['state'] == 'needs_look' else None
                if item is not None:
                    moved.append({'element': element_id, 'kind': item['kind'], 'title': item['title'], 'reason': item['reason'] or item['stale_word'] or item['reason_hidden']})
        finally:
            conn.close()
    return {'moved': moved, 'datasets': [w['name'] for w in written if w['created_version']], 'boards': boards}
