"""Official GOAT split. Test items are never a place to choose a threshold.

Loth, Sarmento, Sarkar, Guo, Barthet, and Sandler, ISMIR 2025.
The audio is CC BY-NC 4.0 and is not in this repository.
"""
from __future__ import annotations

# The seven official test items. Item 60 is still held out of development:
# its fine-alignment is below the authors' 0.75 amplifier-render cutoff, so it
# is reported separately and left out of the primary test mean.
OFFICIAL_TEST = (35, 60, 103, 118, 152, 156, 166)
DIAGNOSTIC_TEST = (60,)
PRIMARY_TEST = tuple(item for item in OFFICIAL_TEST if item not in DIAGNOSTIC_TEST)


class HeldOutItem(Exception):
    """A development run was pointed at an official test item."""


def split_of(item_id: int) -> str:
    return 'test' if int(item_id) in OFFICIAL_TEST else 'train'


def primary(item_id: int) -> bool:
    """False for the low-alignment diagnostic test item."""
    return int(item_id) not in DIAGNOSTIC_TEST


def require_development(item_ids):
    """Raise if a choice of rule would be made on held-out items."""
    banned = sorted(int(i) for i in item_ids if int(i) in OFFICIAL_TEST)
    if banned:
        raise HeldOutItem(
            'Official test items are not for choosing a threshold or a model: '
            + ', '.join(f'item_{i}' for i in banned)
        )
