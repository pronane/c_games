from benchmarks.fullband import gate


def _result(**f1):
    items = {k: {'f1': v} for k, v in f1.items()}
    return {'items': items, 'mean_f1': sum(f1.values()) / len(f1)}


def test_a_candidate_passes_only_with_a_clear_gain_and_no_item_falling():
    base = _result(a=0.20, b=0.40, c=0.60)
    assert gate.verdict(base, _result(a=0.30, b=0.46, c=0.62))['passes']
    # A better mean that sacrifices one song does not pass.
    fell = gate.verdict(base, _result(a=0.45, b=0.55, c=0.50))
    assert not fell['passes'] and list(fell['items_that_fell']) == ['c']
    # Nor does a gain too small to tell from noise, or a candidate scored on fewer songs.
    assert not gate.verdict(base, _result(a=0.22, b=0.42, c=0.62))['passes']
    assert gate.verdict(base, _result(a=0.40, b=0.60))['items_missing'] == ['c']
