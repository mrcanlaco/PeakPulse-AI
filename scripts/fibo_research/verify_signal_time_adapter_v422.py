"""Registered representation-only repair; retain the original failed attempt."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import verify_signal_readiness_v422 as v
import signal_time_adapter_v422 as adapter

r = v.r
ART = v.ART


def test_counts():
    suites = list(ET.parse(ART / 'TIME_ADAPTER_TESTS.xml').getroot().iter('testsuite'))
    counts = {k: sum(int(a.get(k, 0)) for a in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert counts == {'tests': 10, 'errors': 0, 'failures': 0, 'skipped': 0}
    return counts


def register():
    p = v.verify_sources()
    assert not (ART / 'TIME_ADAPTER_PROTOCOL.json').exists()
    test_counts()
    case = p['cases'][0]
    t = r.utc(case['as_of'])
    h = v.load_hours(case['view'], t)
    expected = v.pd.date_range(t-v.pd.Timedelta(hours=24), periods=24, freq='h')
    observed = h.index[-24:]
    assert not observed.equals(expected) and (observed == expected).all()
    assert observed.as_unit('ns').equals(expected.as_unit('ns'))
    proof = {'case_id': case['id'], 'observed_dtype': str(observed.dtype), 'expected_dtype': str(expected.dtype),
        'all_timestamps_equal': True, 'original_index_equals': False, 'normalized_index_equals': True,
        'failure': 'Registered run stopped before saving its first case; no failing case was removed.',
        'original_protocol_sha256': r.sha(ART / 'PROTOCOL.json')}
    r.save(ART / 'TIME_REPRESENTATION_FAILURE.json', proof)
    sources = [Path(__file__), Path(adapter.__file__),
               v.ROOT / 'tests/unit/fibo_short/test_signal_time_adapter_v422.py']
    r.save(ART / 'TIME_ADAPTER_PROTOCOL.json', {'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'parent_protocol_sha256': r.sha(ART / 'PROTOCOL.json'),
        'failure_evidence_sha256': r.sha(ART / 'TIME_REPRESENTATION_FAILURE.json'),
        'sources': {str(p): r.sha(p) for p in sources},
        'tests_sha256': r.sha(ART / 'TIME_ADAPTER_TESTS.xml'),
        'scope': 'Normalize timestamp storage resolution to nanoseconds; preserve exact instants and values.',
        'signal_rules_changed': False, 'sample_changed': False, 'old_files_modified': False})
    print({'adapter_registered': True, 'tests': test_counts()}, flush=True)


def verify():
    v.verify_sources()
    p = r.read(ART / 'TIME_ADAPTER_PROTOCOL.json')
    assert p['parent_protocol_sha256'] == r.sha(ART / 'PROTOCOL.json')
    assert p['failure_evidence_sha256'] == r.sha(ART / 'TIME_REPRESENTATION_FAILURE.json')
    assert p['tests_sha256'] == r.sha(ART / 'TIME_ADAPTER_TESTS.xml')
    for source, digest in p['sources'].items():
        assert r.sha(source) == digest
    return test_counts()


def run():
    counts = verify()
    v.signal = adapter
    v.run()
    result = r.read(ART / 'VERIFICATION.json')
    for key, val in counts.items():
        result['tests'][key] += val
    result['time_adapter_protocol_sha256'] = r.sha(ART / 'TIME_ADAPTER_PROTOCOL.json')
    result['timestamp_resolution_repair'] = 'Validated ns/us/ms equivalence; no market value or signal rule changed.'
    r.save(ART / 'VERIFICATION.json', result)


def publish():
    verify()
    result = r.read(ART / 'VERIFICATION.json')
    assert result['tests']['tests'] == 16
    assert result['time_adapter_protocol_sha256'] == r.sha(ART / 'TIME_ADAPTER_PROTOCOL.json')
    original_render = v.report_text
    def render(d):
        return original_render(d) + ('\n## Chuẩn hóa thời gian đã kiểm chứng\n\n'
            'Lần đối chiếu đầu tiên phát hiện phép so sánh chỉ mục coi ns và us là khác nhau '
            'dù mọi thời điểm đều bằng nhau. Đã lưu nguyên bằng chứng lỗi, nguồn ban đầu và '
            'bổ sung lớp chuẩn hóa về ns; dữ liệu lệch lưới ở mức nano giây vẫn bị từ chối. '
            'Đường gọi đã được kiểm chứng là `signal_time_adapter_v422.closed_signal_snapshots`; '
            'không dùng trực tiếp wrapper ban đầu mà bỏ qua lớp chuẩn hóa này. '
            'Không thay đổi công thức, mẫu kiểm tra hay giá thị trường.\n')
    v.report_text = render
    v.publish()
    checkpoint = r.read(ART / 'CHECKPOINT.json')
    checkpoint['additional_sources'].update({str(Path(p).relative_to(v.ROOT)): h
        for p, h in r.read(ART / 'TIME_ADAPTER_PROTOCOL.json')['sources'].items()})
    r.save(ART / 'CHECKPOINT.json', checkpoint)
    for name, digest in checkpoint['files'].items():
        assert r.sha(ART / name) == digest
    for name, digest in checkpoint['additional_sources'].items():
        assert r.sha(v.ROOT / name) == digest
    print({'all_checkpoint_hashes_verified': True, 'sources': len(checkpoint['additional_sources'])}, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=('register', 'run', 'publish'))
    globals()[p.parse_args().command]()
